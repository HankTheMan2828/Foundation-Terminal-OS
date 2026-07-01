"""The visible incident ledger (spec §6) — TIMESTAMPS ONLY.

Hard rule: what the operator can see is dates/times of logged actions and
NOTHING else — no category, no severity, no description, no content. This is a
deliberate design choice: the operator must not be able to reason about what
tripped a flag.

There are two stores and they must never be confused:
  * ledger.timestamps  — this file. Timestamps only. Readable for display,
    piped to eDP-2 on keyboard detach.
  * incidents.db       — the full detail (what/why/content). frank:frank 0600.
    Never surfaced through any interface. Written by incidents.py, not here.

Format is machine-oriented (compact ISO 8601 basic), per spec §6 — for
efficient parsing/writing, not casual human readability. Daily reset (§6)
truncates it, alongside the AI context.
"""
from __future__ import annotations

import time
from pathlib import Path


class TimestampLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def record(self, ts: float | None = None) -> str:
        """Append a single timestamp for a logged action. Returns the line."""
        ts = time.time() if ts is None else ts
        # Compact basic ISO 8601 in UTC: 20260701T134501Z — machine-parseable.
        line = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))
        with self.path.open("a") as fh:
            fh.write(line + "\n")
        return line

    def read(self, limit: int = 500) -> list[str]:
        try:
            return self.path.read_text().splitlines()[-limit:]
        except OSError:
            return []

    def reset_daily(self) -> None:
        """Truncate the visible ledger (spec §6 daily reset)."""
        self.path.write_text("")
