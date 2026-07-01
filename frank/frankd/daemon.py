"""frankd — the overseer daemon main loop (spec §6).

Wires the pieces: collect events -> rule engine classifies (offline) -> enforcer
escalates -> AI phrases commentary (flagged events only) -> ledger records a
timestamp, incidents store records full detail (frank-only) -> pending warn is
queued for the Hub to *display*, and the current lock decision is published for
the ROOT enforcer to *apply*.

Three tiers now feed the same Enforcer (this session added the second two):
  1. Rule engine (rules.py) — realtime, offline, every tick. Primary/always-on.
  2. Sorting/sifting Frank (triage.py) — periodic, organizes recent incidents
     + raw log content into a digest. Never enforces anything itself.
  3. The Overseer (overseer.py) — "main Frank." Reads the digests on its own
     schedule, or immediately on a SERIOUS finding, and MAY produce its own
     Finding, which flows through the identical `_handle_finding` path as a
     rule-engine Finding — same ledger entry, same incidents record, same
     Enforcer state machine, same hard ceiling.

The operator has NO power over Frank. Nothing here reads operator-supplied
configuration at runtime and there is no command that lets the operator tune,
disable, or influence detection or enforcement. Sensitivity is loaded once from
Frank's root-owned config and can only be changed by root (not the operator).

Runs as system user `frank`, isolated from the operator (spec §6). Reset is
time-of-day driven; lockout duration is severity driven — kept distinct.
"""
from __future__ import annotations

import time
from collections import deque

from . import config, lockstate, sources
from .enforcement import ReactionKind, UserEnforcers
from .eventlog import EventLog
from .incidents import IncidentStore
from .ledger import TimestampLedger
from .mistral import build as build_commentator
from .model import Severity, Source
from .overseer import Overseer, VerdictLog
from .rules import RuleEngine
from .triage import TriageEngine, TriageStore

# Only these sources carry free text worth persisting to the raw event log
# for later content review — same restriction triage.py applies when reading
# it back. Process/network events are numeric/destination signals already
# handled by the rule engine; logging them here would be pure volume.
_LOGGABLE_SOURCES = {Source.SHELL, Source.BROWSER}

# How far back an Overseer check-in's activity snapshot looks (spec: it should
# see "the user's current happenings" at check-in time, not just history).
_SNAPSHOT_WINDOW_SECONDS = 300
_SNAPSHOT_MAX_LINES = 20


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
        self.triage = TriageEngine(self.incidents, self.eventlog, self.triage_store)
        self.overseer = Overseer(self.triage_store, self.incidents, self.eventlog,
                                  VerdictLog(self.cfg.verdicts_path))
        self.commentator = build_commentator()
        self.poll_interval = poll_interval
        self.lock_state_path = self.cfg.incidents_path.parent / "lockout.state"
        self._src_state: dict = {}
        self._pending: deque = deque(maxlen=32)   # warnings awaiting Hub display
        self._last_reset_day = time.gmtime().tm_yday
        now = time.time()
        self._last_triage_run = now
        self._last_overseer_checkin = now
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
            return (f"lockout scope=session user={user} "
                    f"remaining={int(lk.end - now)}")
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
        lockstate.write_public(self.cfg.login_locks_path, self.enforcers, now)

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
        server = IPCServer(self.cfg.ipc_socket, self.poll_message)  # read-only
        server.start()
        try:
            while True:
                self.tick()
                time.sleep(self.poll_interval)
        finally:
            server.stop()


def main() -> int:  # pragma: no cover
    Frank().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
