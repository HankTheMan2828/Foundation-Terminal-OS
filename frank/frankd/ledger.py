"""The visible incident ledger (spec §6) — TIMESTAMPS ONLY.

Hard rule: what the operator can see is dates/times of logged actions and
NOTHING else — no category, no severity, no description, no content. This is a
deliberate design choice: the operator must not be able to reason about what
tripped a flag.

There are two stores and they must never be confused:
  * ledger.timestamps  — this file. Timestamps only. Readable for display;
    some hardware profiles pipe it to a second panel on keyboard detach
    (see profiles/zenbook-duo-2024/), but that delivery mechanism is optional
    and lives outside this module.
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
        # The ledger is the one Frank output the operator is MEANT to read
        # (timestamps only, §6). Make the file world-readable so the Hub — which
        # runs as the operator, not frank — can actually display it. This leaks
        # nothing: it is timestamps and nothing else; the detail store
        # (incidents.db) stays 0600 frank-only. Best-effort: a chmod failure
        # (e.g. off-target dev on a filesystem without POSIX modes) is harmless.
        try:
            self.path.chmod(0o644)
        except OSError:
            pass

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
