"""frankd — the overseer daemon main loop (spec §6).

Wires the pieces: collect events -> rule engine classifies (offline) -> enforcer
escalates -> AI phrases commentary (flagged events only) -> ledger records a
timestamp, incidents store records full detail (frank-only) -> pending warn is
queued for the Hub to *display*, and the current lock decision is published for
the ROOT enforcer to *apply*.

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
from .enforcement import Enforcer, ReactionKind
from .incidents import IncidentStore
from .ledger import TimestampLedger
from .mistral import build as build_commentator
from .rules import RuleEngine


class Frank:
    def __init__(self, cfg: config.FrankConfig | None = None, *, poll_interval: float = 2.0):
        self.cfg = cfg or config.load()
        self.engine = RuleEngine.from_dir(config.RULES_DIR, self.cfg.sensitivity)
        self.enforcer = Enforcer(self.cfg.enforcement)
        self.ledger = TimestampLedger(self.cfg.ledger_path)
        self.incidents = IncidentStore(self.cfg.incidents_path)
        self.commentator = build_commentator()
        self.poll_interval = poll_interval
        self.lock_state_path = self.cfg.incidents_path.parent / "lockout.state"
        self._src_state: dict = {}
        self._pending: deque = deque(maxlen=32)   # warnings awaiting Hub display
        self._last_reset_day = time.gmtime().tm_yday
        # Re-arm a still-valid MACHINE lock from a previous boot (spec §6).
        lockstate.restore_machine_lock(self.enforcer, self.lock_state_path, time.time())

    # NOTE: there is deliberately NO set_sensitivity / no operator-facing mutator.
    # Sensitivity is fixed from root-owned config at load; the operator cannot
    # change it, or anything else about Frank, from within the running OS.

    def poll_message(self) -> str:
        """Hub asks for something to DISPLAY. Read-only; grants no authority."""
        if self._pending:
            return self._pending.popleft()
        now = time.time()
        if self.enforcer.is_locked(now):
            return (f"lockout scope={self.enforcer.scope().value} "
                    f"remaining={int(self.enforcer.remaining(now))}")
        return "NONE"

    # ── processing ────────────────────────────────────────────────────────────
    def _handle_finding(self, finding, now: float) -> None:
        reaction = self.enforcer.process(finding, now)
        # Every logged action gets a timestamp in the visible ledger (§6).
        self.ledger.record(now)
        commentary = ""
        # Commentary only on user-facing reactions (flagged events), never on
        # silent observations — keeps AI cost down (spec §6).
        if reaction.kind in (ReactionKind.WARN, ReactionKind.LOCKOUT):
            commentary = self.commentator.comment(reaction)
            self._queue_for_hub(reaction, commentary)
        # Full detail always recorded, frank-only.
        self.incidents.record(finding, reaction.kind.value, commentary)

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
            for finding in self.engine.classify(event):
                self._handle_finding(finding, now)
        # Publish the current lock decision for the root enforcer every tick,
        # so it applies new locks and releases expired ones promptly.
        lockstate.write(self.lock_state_path, self.enforcer, now)

    def _maybe_daily_reset(self, now: float) -> None:
        """Time-of-day reset of ledger + working memory (spec §6). Not lockouts."""
        lt = time.localtime(now)
        if lt.tm_yday != self._last_reset_day and lt.tm_hour >= self.cfg.reset_hour:
            self.ledger.reset_daily()
            self.enforcer.reset_daily()
            self._last_reset_day = lt.tm_yday

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
