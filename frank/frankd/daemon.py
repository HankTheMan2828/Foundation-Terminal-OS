"""frankd — the overseer daemon main loop (spec §6).

Wires the pieces: collect events -> rule engine classifies (offline) -> enforcer
escalates -> AI phrases commentary (flagged events only) -> ledger records a
timestamp, incidents store records full detail (frank-only) -> pending warn is
queued for the Hub to *display*, and the current lock decision is published for
the ROOT enforcer to *apply*.

Three tiers feed the same Enforcer:
  1. Rule engine (rules.py) — realtime, offline, every tick. Primary/always-on.
  2. Sorting/sifting Frank (triage.py) — periodic, organizes recent incidents
     + raw log content into a digest. Never enforces anything itself.
  3. The Overseer (overseer.py) — "main Frank." Reads the digests on its own
     schedule, or immediately on a SERIOUS finding, and MAY produce its own
     Finding, which flows through the identical `_handle_finding` path as a
     rule-engine Finding — same ledger entry, same incidents record, same
     Enforcer state machine, same hard ceiling.

Operator direction: Frank is a primarily rule-based overseer system
(OPEN-QUESTIONS.md §5). The Overseer's verdicts come from a deterministic
Rulebook; its AI brain and the AI phrasing of Frank's voice are both opt-in
flags in root-only config (overseer.ai_enabled / commentary.ai_enabled,
default off) — with them off, nothing in this loop ever needs a network.

The operator has NO power over Frank. Nothing here reads operator-supplied
configuration at runtime and there is no command that lets the operator tune,
disable, or influence detection or enforcement. Sensitivity is loaded once from
Frank's root-owned config and can only be changed by root (not the operator).

Runs as system user `frank`, isolated from the operator (spec §6). Reset is
time-of-day driven; lockout duration is severity driven — kept distinct.
"""
from __future__ import annotations

import time
import traceback
from collections import deque
from pathlib import Path

from . import ai, config, lockstate, negotiation, sources
from .enforcement import DEFAULT_USER, ReactionKind, UserEnforcers
from .eventlog import EventLog
from .incidents import IncidentStore
from .ledger import TimestampLedger
from .mistral import build as build_commentator, care_line
from .model import Severity, Source
from .overseer import Overseer, Rulebook, VerdictLog
from .rules import RuleEngine
from .triage import TriageEngine, TriageStore
from .violations import ViolationCounts

# Only these sources carry free text worth persisting to the raw event log
# for later content review — same restriction triage.py applies when reading
# it back. Process/network events are numeric/destination signals already
# handled by the rule engine; logging them here would be pure volume.
# ACTIVITY is the Hub's per-action feed (programs opened, notes/files edited,
# screens navigated, chat sent) — the main content stream on this OS, so it
# belongs in the base log the sift/Overseer tiers read.
_LOGGABLE_SOURCES = {Source.SHELL, Source.BROWSER, Source.ACTIVITY}

# How far back an Overseer check-in's activity snapshot looks (spec: it should
# see "the user's current happenings" at check-in time, not just history).
_SNAPSHOT_WINDOW_SECONDS = 300
_SNAPSHOT_MAX_LINES = 20

# Realtime rules whose OBSERVE findings are harm-TO-USER concerns: Frank speaks a
# SUPPORTIVE line rather than doing nothing, but never warns/locks (that would be
# the wrong response). docs/FRANK-LOCAL-AI.md §2/§3.
_CARE_RULE_PREFIXES = ("legal-self-harm",)
# Don't repeat a care message more often than this — a self-harm phrase saved
# repeatedly shouldn't spam the user.
_CARE_COOLDOWN_SECONDS = 300

# Operator-READABLE health breadcrumb. Spec §6 keeps Frank's *findings* private,
# but whether the daemon is even alive — and why it died — must be diagnosable on
# a no-shell locked kiosk. Written under /run/frank (0755 frank) at mode 0644 so
# the Hub's System Status can read it and show the operator the real startup
# error instead of a bare "non-functional". Carries NO finding detail — only a
# status tag and, on failure, the traceback of what stopped Frank from running.
_HEALTH_PATH = Path("/run/frank/frankd.health")


def _write_health(status: str, detail: str = "") -> None:
    """Record the daemon's liveness / last fatal error where the operator can
    see it. Best-effort: a health write must never itself crash Frank."""
    try:
        _HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HEALTH_PATH.write_text(f"status={status}\nts={int(time.time())}\n{detail}")
        try:
            _HEALTH_PATH.chmod(0o644)
        except OSError:
            pass
    except OSError:
        pass


class Frank:
    def __init__(self, cfg: config.FrankConfig | None = None, *, poll_interval: float = 2.0):
        self.cfg = cfg or config.load()
        self.engine = RuleEngine.from_dir(config.RULES_DIR, self.cfg.sensitivity)
        # Per-user records; machine locks global (docs/USERS.md). Same single
        # enforcement path — UserEnforcers only routes by the event's user.
        self.enforcers = UserEnforcers(self.cfg.enforcement)
        self.ledger = TimestampLedger(self.cfg.ledger_path)
        self.incidents = IncidentStore(self.cfg.incidents_path)
        self.eventlog = EventLog(self.cfg.events_path)
        self.triage_store = TriageStore(self.cfg.triage_path)
        # The content sensor's backend is operator-selectable (default: the
        # local model, installed with the OS — docs/FRANK-LOCAL-AI.md).
        self.triage = TriageEngine(self.incidents, self.eventlog, self.triage_store,
                                   sifter=ai.build_sifter(self.cfg.sift))
        self.overseer = Overseer(
            self.triage_store, self.incidents, self.eventlog,
            VerdictLog(self.cfg.verdicts_path),
            rulebook=Rulebook(self.cfg.overseer),
            # AI second opinion only with the root-only opt-in flag (plus a
            # key); the deterministic rulebook is the brain either way.
            brain=(ai.build_overseer_brain() if self.cfg.overseer.ai_enabled else None))
        self.commentator = build_commentator(self.cfg.commentary.ai_enabled)
        # Rule-bounded negotiable-lockout engine. Its advisor uses the same
        # local-model backend when local sifting is on; else a deterministic
        # offline heuristic. The LLM only advises — the config bounds decide.
        self.negotiator = negotiation.NegotiationEngine(
            self.cfg.negotiation, negotiation.build_advisor(self.cfg.sift))
        # Per-user violation counts, persistent — published (counts only) in
        # the public login summary so the roster can show them (docs/USERS.md).
        self.violations = ViolationCounts(self.cfg.violations_path)
        self.poll_interval = poll_interval
        self.lock_state_path = self.cfg.incidents_path.parent / "lockout.state"
        self._src_state: dict = {}
        self._pending: deque = deque(maxlen=32)   # warnings awaiting Hub display
        self._last_reset_day = time.gmtime().tm_yday
        now = time.time()
        self._last_triage_run = now
        self._last_overseer_checkin = now
        self._last_care = float("-inf")   # allow the very first care message
        # Re-arm a still-valid MACHINE lock from a previous boot (spec §6).
        lockstate.restore_machine_lock(self.enforcers, self.lock_state_path, now)

    # NOTE: there is deliberately NO set_sensitivity / no operator-facing mutator.
    # Sensitivity is fixed from root-owned config at load; the operator cannot
    # change it, or anything else about Frank, from within the running OS.

    def poll_message(self) -> str:
        """Hub asks for something to DISPLAY. Read-only; grants no authority."""
        if self._pending:
            return self._pending.popleft()
        now = time.time()
        machine = self.enforcers.machine_lockout(now)
        if machine is not None:
            return (f"lockout scope=machine "
                    f"remaining={int(machine[1].end - now)}")
        sessions = self.enforcers.session_lockouts(now)
        if sessions:
            user, lk = next(iter(sessions.items()))
            # negotiable flag tells the Hub whether to offer the plea screen.
            negotiable = 1 if (lk.negotiable
                               and lk.attempts_used < self.cfg.negotiation.max_attempts
                               and self.cfg.negotiation.enabled) else 0
            return (f"lockout scope=session user={user} "
                    f"remaining={int(lk.end - now)} negotiable={negotiable}")
        return "NONE"

    # ── processing ────────────────────────────────────────────────────────────
    def _handle_finding(self, finding, now: float) -> None:
        reaction = self.enforcers.process(finding, now)
        # Every logged action gets a timestamp in the visible ledger (§6).
        self.ledger.record(now)
        commentary = ""
        # Commentary only on user-facing reactions (flagged events), never on
        # silent observations — keeps AI cost down (spec §6).
        if reaction.kind in (ReactionKind.WARN, ReactionKind.LOCKOUT):
            commentary = self.commentator.comment(reaction)
            self._queue_for_hub(reaction, commentary)
            # A user-facing reaction is a violation on the person's permanent
            # count (silent observations aren't). Count only, never detail.
            self.violations.increment(finding.event.user or DEFAULT_USER)
        # Harm-to-user care path: an OBSERVE finding from a care rule gets a
        # SUPPORTIVE spoken line (baked words; the rule decides WHEN), never a
        # punitive reaction. Rate-limited so it can't spam.
        if (reaction.kind is ReactionKind.OBSERVE
                and any(finding.rule_id.startswith(p) for p in _CARE_RULE_PREFIXES)
                and now - self._last_care >= _CARE_COOLDOWN_SECONDS):
            self._pending.append(f"care msg={care_line()}")
            self._last_care = now
        # Full detail always recorded, frank-only.
        self.incidents.record(finding, reaction.kind.value, commentary, now=now)
        # Immediate Overseer wake on SERIOUS (operator-confirmed scope this
        # session: SERIOUS only, not every lockout). Guard against a synthetic
        # Overseer Finding re-triggering itself — it already got its review.
        if (self.cfg.overseer.wake_on_serious
                and finding.severity is Severity.SERIOUS
                and finding.event.source is not Source.OVERSEER):
            for extra in self.overseer.on_serious_finding(finding, now):
                self._handle_finding(extra, now)

    def negotiate(self, plea: str, now: float | None = None) -> str:
        """Handle a `negotiate` plea from the Hub against the active user's
        lockout. Frank decides (rule-bounded); the user cannot force release.
        Attributes to the active-user file, never to anything on the wire."""
        now = time.time() if now is None else now
        user = sources.active_user() or DEFAULT_USER
        enforcer = self.enforcers.enforcer_for(user)
        result = self.negotiator.negotiate(enforcer, plea, now)
        # A negotiation is a logged action (§6) and may have changed the timer —
        # republish the lock decision at once so the root enforcer/login reflect it.
        self.ledger.record(now)
        lockstate.write(self.lock_state_path, self.enforcers, now)
        lockstate.write_public(self.cfg.login_locks_path, self.enforcers, now,
                               violations=self.violations.counts)
        return (f"negotiate outcome={result.outcome} "
                f"removed={int(result.removed_seconds)} "
                f"remaining={int(result.remaining_seconds)} msg={result.message}")

    def _queue_for_hub(self, reaction, commentary: str) -> None:
        # Warnings are DISPLAYED by the Hub. Lockouts are ENFORCED by the root
        # enforcer (via lockout.state); the Hub only reflects them.
        if reaction.kind is ReactionKind.LOCKOUT:
            msg = (f"lockout scope={reaction.scope.value} "
                   f"end={int(reaction.lockout_end or 0)} msg={commentary}")
        else:
            msg = f"warn delivery={reaction.delivery.value} msg={commentary}"
        self._pending.append(msg)

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._maybe_daily_reset(now)
        for event in sources.collect(self._src_state):
            if event.source in _LOGGABLE_SOURCES:
                self.eventlog.record(event)   # the "base logs" triage/overseer sift
            for finding in self.engine.classify(event):
                self._handle_finding(finding, now)
        self._maybe_run_triage(now)
        self._maybe_overseer_checkin(now)
        # Publish the current lock decision for the root enforcer every tick,
        # so it applies new locks and releases expired ones promptly — plus
        # the public usernames+timestamps summary the login screen gates on.
        lockstate.write(self.lock_state_path, self.enforcers, now)
        lockstate.write_public(self.cfg.login_locks_path, self.enforcers, now,
                               violations=self.violations.counts)

    def _maybe_daily_reset(self, now: float) -> None:
        """Time-of-day reset of ledger + working memory (spec §6). Not lockouts."""
        lt = time.localtime(now)
        if lt.tm_yday != self._last_reset_day and lt.tm_hour >= self.cfg.reset_hour:
            self.ledger.reset_daily()
            self.enforcers.reset_daily()
            self.eventlog.prune(now)   # own retention policy — see eventlog.py
            self._last_reset_day = lt.tm_yday

    def _maybe_run_triage(self, now: float) -> None:
        """Sorting/sifting Frank's own cadence — independent of, and much
        shorter than, the Overseer's check-in interval."""
        if now - self._last_triage_run >= self.cfg.triage.interval_seconds:
            self.triage.run(now)
            self._last_triage_run = now

    def _maybe_overseer_checkin(self, now: float) -> None:
        """Main Frank's periodic path (the SERIOUS-trigger path fires from
        `_handle_finding` instead, immediately, independent of this cadence)."""
        if now - self._last_overseer_checkin >= self.cfg.overseer.checkin_interval_seconds:
            for finding in self.overseer.check_in(now, self._activity_snapshot(now)):
                self._handle_finding(finding, now)
            self._last_overseer_checkin = now

    def _activity_snapshot(self, now: float) -> str:
        """What Main Frank sees of "the user's current happenings" at
        check-in — a bounded recent slice of the raw event log, not a live
        process dump (keeps this deterministic/testable and cheap)."""
        recent = self.eventlog.between(now - _SNAPSHOT_WINDOW_SECONDS, now)
        machine = self.enforcers.machine_lockout(now)
        sessions = self.enforcers.session_lockouts(now)
        if machine is not None:
            lock_desc = "active scope=machine"
        elif sessions:
            lock_desc = f"active scope=session users={','.join(sorted(sessions))}"
        else:
            lock_desc = "none"
        lines = [f"lockout: {lock_desc}"]
        lines.append(f"last {_SNAPSHOT_WINDOW_SECONDS}s of activity ({len(recent)} events):")
        for entry in recent[-_SNAPSHOT_MAX_LINES:]:
            lines.append(f"  [{entry.get('source')}] {entry.get('text')}")
        return "\n".join(lines)

    def run(self) -> None:  # pragma: no cover - long-running loop
        from .ipc import IPCServer
        # poll = read-only status; negotiate = a plea Frank decides on (still no
        # authority to change Frank — docs/FRANK-LOCAL-AI.md §4).
        server = IPCServer(self.cfg.ipc_socket, self.poll_message,
                           on_negotiate=self.negotiate)
        server.start()
        _write_health("running")
        try:
            while True:
                try:
                    self.tick()
                except Exception:
                    # One bad tick must not crash-loop the whole overseer (which
                    # would take detection + enforcement down with it). Record why
                    # and keep going — the rule engine is the primary, always-on
                    # mechanism (spec §6) and should survive a transient collector
                    # or store error.
                    _write_health("tick-error", traceback.format_exc())
                time.sleep(self.poll_interval)
        finally:
            server.stop()


def main() -> int:  # pragma: no cover
    # Startup (import already succeeded to get here) must not fail invisibly: on
    # a locked kiosk the operator can't read the journal, so capture any crash in
    # the operator-readable health file before re-raising for systemd to log.
    # Two phases, captured separately: construction, and run() (which binds the
    # IPC socket and enters the loop) — a socket-bind failure is exactly the kind
    # of run-time crash that leaves frankd "non-functional" with no clue why.
    try:
        frank = Frank()
    except Exception:
        _write_health("startup-error", traceback.format_exc())
        raise
    try:
        frank.run()
    except Exception:
        _write_health("run-error", traceback.format_exc())
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
