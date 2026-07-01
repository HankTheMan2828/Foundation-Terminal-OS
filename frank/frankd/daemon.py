"""frankd — the overseer daemon main loop (spec §6).

Wires the pieces: collect events -> rule engine classifies (offline) -> enforcer
escalates -> AI phrases commentary (flagged events only) -> ledger records a
timestamp, incidents store records full detail (frank-only) -> pending
warn/lockout is queued for the Hub to poll.

Runs as system user `frank`, isolated from the operator (spec §6). Reset is
time-of-day driven; lockout duration is severity driven — kept distinct.
"""
from __future__ import annotations

import time
from collections import deque

from . import config, sources
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
        self._src_state: dict = {}
        self._pending: deque = deque(maxlen=32)   # warn/lockout awaiting Hub poll
        self._last_reset_day = time.gmtime().tm_yday

    # ── the single knob exposed to the operator (spec §5) ─────────────────────
    def set_sensitivity(self, level: int) -> str:
        level = self.cfg.clamp_sensitivity(level)
        self.cfg.sensitivity = level
        self.engine.sensitivity = level
        return f"OK sensitivity={level}"

    def poll_message(self) -> str:
        """Hub asks for a pending warn/lockout. Returns one line or 'NONE'."""
        if self._pending:
            return self._pending.popleft()
        if self.enforcer.is_locked(time.time()):
            end = self.enforcer.remaining(time.time())
            scope = self.enforcer.scope().value
            return f"lockout scope={scope} remaining={int(end)}"
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
        if reaction.kind is ReactionKind.LOCKOUT:
            msg = (f"lockout scope={reaction.scope.value} "
                   f"end={int(reaction.lockout_end or 0)} msg={commentary}")
        else:
            delivery = reaction.delivery.value
            msg = f"warn delivery={delivery} msg={commentary}"
        self._pending.append(msg)

    def tick(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._maybe_daily_reset(now)
        for event in sources.collect(self._src_state):
            for finding in self.engine.classify(event):
                self._handle_finding(finding, now)

    def _maybe_daily_reset(self, now: float) -> None:
        """Time-of-day reset of ledger + working memory (spec §6). Not lockouts."""
        lt = time.localtime(now)
        if lt.tm_yday != self._last_reset_day and lt.tm_hour >= self.cfg.reset_hour:
            self.ledger.reset_daily()
            self.enforcer.reset_daily()
            self._last_reset_day = lt.tm_yday

    def run(self) -> None:  # pragma: no cover - long-running loop
        from .ipc import IPCServer
        server = IPCServer(self.cfg.ipc_socket, self.set_sensitivity, self.poll_message)
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
