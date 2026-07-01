"""Warning/lockout enforcement (spec §6).

Invariants this module guarantees (each is covered by tests/test_enforcement.py):

  * Warnings escalate, scaled by severity. A serious finding skips straight to
    action (fewer/zero warnings); minor findings accrue more warnings first.
  * Lockout SCOPE is severity-based: minor/elevated -> this session/console;
    serious -> whole machine.
  * Lockout DURATION is severity-based. The hard cooldown is an ABSOLUTE
    ceiling: Frank may EXTEND an active lockout up to the ceiling for further
    severe findings, but can NEVER exceed or bypass it. It always expires.
  * Manual override exists but must be verified by Frank — it is not a plain
    bypass, and it is recorded.
  * Daily reset clears working escalation memory (like context/ledger); it does
    NOT touch an active lockout. severity -> duration; time-of-day -> reset.

The engine is pure and clock-injected (`now` passed in) so it's fully testable
offline with no sleeping.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .config import EnforcementConfig
from .model import Finding, Severity, Track


class Scope(enum.Enum):
    SESSION = "session"     # lock this console/session only (spec §6, minor)
    MACHINE = "machine"     # lock the whole machine (spec §6, serious)


class Delivery(enum.Enum):
    STATUS_BAR = "status_bar"   # normal warnings (spec §6)
    BANNER = "banner"           # serious: full-screen interrupting banner (spec §6)


class ReactionKind(enum.Enum):
    OBSERVE = "observe"     # recorded to ledger; no user-facing change
    WARN = "warn"           # escalating warning
    LOCKOUT = "lockout"     # entered or extended a lockout


@dataclass
class Reaction:
    kind: ReactionKind
    delivery: Delivery
    severity: Severity
    track: Track
    scope: Scope | None = None
    warnings_remaining: int | None = None
    lockout_end: float | None = None
    extended: bool = False


@dataclass
class _TrackState:
    score: int = 0
    max_severity: Severity = Severity.MINOR


@dataclass
class Lockout:
    scope: Scope
    start: float
    end: float
    ceiling_end: float          # start + hard ceiling; end may never exceed this
    trigger_severity: Severity

    def active(self, now: float) -> bool:
        return now < self.end


class Enforcer:
    def __init__(self, config: EnforcementConfig | None = None):
        self.cfg = config or EnforcementConfig()
        self.tracks: dict[Track, _TrackState] = {t: _TrackState() for t in Track}
        self.lockout: Lockout | None = None

    # ── queries ──────────────────────────────────────────────────────────────
    def is_locked(self, now: float) -> bool:
        if self.lockout and not self.lockout.active(now):
            self.lockout = None          # expired: always eventually clears
        return self.lockout is not None

    def remaining(self, now: float) -> float:
        if self.is_locked(now):
            return max(0.0, self.lockout.end - now)
        return 0.0

    def scope(self) -> Scope | None:
        return self.lockout.scope if self.lockout else None

    # ── the main entry point ─────────────────────────────────────────────────
    def process(self, finding: Finding, now: float) -> Reaction:
        weight = self.cfg.weights[finding.severity]
        delivery = (Delivery.BANNER if finding.severity is Severity.SERIOUS
                    else Delivery.STATUS_BAR)

        # Already locked: a further SERIOUS finding may EXTEND, within ceiling.
        if self.is_locked(now):
            if finding.severity is Severity.SERIOUS:
                self._extend(finding, now)
                return Reaction(ReactionKind.LOCKOUT, Delivery.BANNER,
                                finding.severity, finding.track,
                                scope=self.lockout.scope,
                                lockout_end=self.lockout.end, extended=True)
            # Non-severe during a lockout: just observed/recorded.
            return Reaction(ReactionKind.OBSERVE, delivery,
                            finding.severity, finding.track)

        # Not locked: accumulate escalation on this track.
        st = self.tracks[finding.track]
        st.score += weight
        st.max_severity = max(st.max_severity, finding.severity)

        if st.score >= self.cfg.warning_threshold:
            return self._enter_lockout(finding.track, now)

        return Reaction(ReactionKind.WARN, delivery, finding.severity,
                        finding.track,
                        warnings_remaining=self.cfg.warning_threshold - st.score)

    # ── lockout transitions ──────────────────────────────────────────────────
    def _enter_lockout(self, track: Track, now: float) -> Reaction:
        st = self.tracks[track]
        trigger = st.max_severity
        scope = Scope.MACHINE if trigger is Severity.SERIOUS else Scope.SESSION
        base = self.cfg.base_lockout_seconds[trigger]
        ceiling_end = now + self.cfg.hard_ceiling_seconds
        end = min(now + base, ceiling_end)      # never exceed the hard ceiling
        self.lockout = Lockout(scope, now, end, ceiling_end, trigger)
        # Reset this track's working escalation; the lockout timer now governs.
        self.tracks[track] = _TrackState()
        return Reaction(ReactionKind.LOCKOUT, Delivery.BANNER, trigger, track,
                        scope=scope, lockout_end=end)

    def _extend(self, finding: Finding, now: float) -> None:
        lk = self.lockout
        assert lk is not None
        # Extend toward — but never past — the ceiling fixed at lockout start.
        lk.end = min(lk.end + self.cfg.extension_seconds, lk.ceiling_end)
        # A machine-scope serious finding escalates scope upward, never down.
        if finding.severity is Severity.SERIOUS:
            lk.scope = Scope.MACHINE
            lk.trigger_severity = Severity.SERIOUS

    # ── override + reset ─────────────────────────────────────────────────────
    def request_override(self, now: float, verified: bool) -> bool:
        """Manual override — must be Frank-verified, not a plain bypass (spec §6).

        `verified` is the outcome of Frank's own verification challenge (issued
        elsewhere; the operator cannot self-approve). Even a verified override is
        recorded by the caller. Returns True if the lockout was lifted.
        """
        if not self.is_locked(now):
            return False
        if not verified:
            return False
        self.lockout = None
        return True

    def reset_daily(self) -> None:
        """Time-of-day reset (spec §6): clear working escalation memory.

        Does NOT touch an active lockout — severity governs lockout duration,
        time-of-day governs context/ledger/working-memory reset. Kept distinct.
        """
        self.tracks = {t: _TrackState() for t in Track}
