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
    last_time: float | None = None


@dataclass
class Lockout:
    scope: Scope
    start: float
    end: float
    ceiling_end: float          # start + hard ceiling; end may never exceed this
    trigger_severity: Severity
    # Negotiation (docs/FRANK-AI-GUARDIAN.md §4). Only SESSION locks are
    # negotiable; MACHINE/serious locks never are — Frank's side always wins.
    negotiable: bool = False
    orig_end: float = 0.0       # the end at entry, for computing served/floor fractions
    attempts_used: int = 0      # pleas entertained so far (capped by config)

    def __post_init__(self) -> None:
        if not self.orig_end:
            self.orig_end = self.end

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
        # OBSERVE is a hard bypass: always recorded, never warns, never locks
        # out, regardless of current lock state or accrued score on its track.
        if finding.severity is Severity.OBSERVE:
            return Reaction(ReactionKind.OBSERVE, Delivery.STATUS_BAR,
                            finding.severity, finding.track)

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

        # Not locked: accumulate escalation on this track. A long-quiet track
        # decays back to zero first — scattered one-offs shouldn't slowly
        # stack toward a lockout the way a burst of activity should.
        st = self.tracks[finding.track]
        if (st.last_time is not None
                and now - st.last_time > self.cfg.track_score_decay_seconds):
            st.score = 0
            st.max_severity = Severity.MINOR
        st.last_time = now
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
        # SESSION locks are negotiable; MACHINE/serious locks never are.
        self.lockout = Lockout(scope, now, end, ceiling_end, trigger,
                               negotiable=(scope is Scope.SESSION), orig_end=end)
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

    # ── negotiation (docs/FRANK-AI-GUARDIAN.md §4) ───────────────────────────
    def reduce_lockout(self, now: float, seconds: float, floor_end: float) -> float:
        """Shorten the active lockout by up to `seconds`, but NEVER below
        `floor_end` (and never below `now`). Returns the seconds actually
        removed. This is the only path negotiation has to the timer, so the
        floor is enforced here, in the same place that owns the ceiling — the
        model that advises a reduction cannot reach past this clamp. If the
        reduction reaches the floor at/behind `now`, the lockout lifts."""
        if not self.is_locked(now):
            return 0.0
        lk = self.lockout
        target = max(floor_end, now, lk.end - max(0.0, seconds))
        removed = max(0.0, lk.end - target)
        lk.end = target
        if lk.end <= now:
            self.lockout = None
        return removed

    def note_negotiation_attempt(self, now: float) -> None:
        if self.is_locked(now):
            self.lockout.attempts_used += 1

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


# ── multi-user coordination (docs/USERS.md) ──────────────────────────────────

DEFAULT_USER = "operator"    # unattributed events land on the session default


class UserEnforcers:
    """Per-user records; machine locks are global.

    Each username gets its own Enforcer — warning scores and SESSION-scope
    lockouts follow the person across logins. A MACHINE-scope lockout,
    whoever triggered it, locks the terminal for everyone: the coordinator
    surfaces it globally rather than per-user.

    This is a router, not a second enforcement path: every Finding still runs
    through Enforcer.process(), so the hard-ceiling/scope/duration invariants
    hold per user exactly as they did for the single-user model.
    """

    def __init__(self, config: EnforcementConfig | None = None):
        self.cfg = config or EnforcementConfig()
        self.users: dict[str, Enforcer] = {}

    def enforcer_for(self, user: str) -> Enforcer:
        user = user or DEFAULT_USER
        if user not in self.users:
            self.users[user] = Enforcer(self.cfg)
        return self.users[user]

    def process(self, finding: Finding, now: float) -> Reaction:
        return self.enforcer_for(finding.event.user).process(finding, now)

    # ── aggregate views ──────────────────────────────────────────────────────
    def machine_lockout(self, now: float) -> tuple[str, Lockout] | None:
        """The active MACHINE lock and who triggered it, if any."""
        for user, enf in self.users.items():
            if enf.is_locked(now) and enf.lockout.scope is Scope.MACHINE:
                return user, enf.lockout
        return None

    def session_lockouts(self, now: float) -> dict[str, Lockout]:
        """Active SESSION locks by user — these follow the person, so the
        login screen refuses them until expiry (docs/USERS.md)."""
        return {user: enf.lockout for user, enf in self.users.items()
                if enf.is_locked(now) and enf.lockout.scope is Scope.SESSION}

    def is_locked(self, user: str, now: float) -> bool:
        """Whether this user may hold the console: their own session lock OR
        anyone's machine lock says no."""
        if self.machine_lockout(now) is not None:
            return True
        return self.enforcer_for(user).is_locked(now)

    def reset_daily(self) -> None:
        for enf in self.users.values():
            enf.reset_daily()
