"""The raw event log — the "base logs" the AI-layer tiers sift (this session).

Distinct from BOTH other stores on purpose:
  * ledger.timestamps  — user-visible, timestamps only.
  * incidents.db        — frank-only, but only RULE MATCHES (what the rule
                           layer already decided to flag).
  * events.log (here)   — frank-only, EVERY content-bearing event, matched or
                           not. This is what makes the periodic AI-layer review
                           possible for categories the rule layer deliberately
                           doesn't keyword-match (see docs/OPEN-QUESTIONS.md
                           §3 — hate-speech/extremism was parked here on
                           purpose: "the operator asked for that broader
                           category to go through a scheduled/periodic review
                           rather than realtime keyword flagging").

Only content-bearing sources are written here (shell/browser/filesystem/
network destination strings) — the daemon does NOT log every process-list
tick, which would be pure volume with nothing for a content review to find.
See daemon.py's call site for exactly which sources it forwards.

Bounded by a retention window (not size), pruned on the same daily-reset tick
as the ledger/context — see prune(). This is intentionally a SEPARATE
retention policy from incidents.db (which is never pruned): raw text volume
here is much higher, and stale raw content earns its keep far less than a
recorded finding does.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .model import Event


class EventLog:
    def __init__(self, path: Path, retention_seconds: float = 3 * 86400):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_seconds = retention_seconds
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def record(self, event: Event) -> None:
        entry = {
            "ts": event.ts,
            "source": event.source.value,
            "text": event.text,
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ── reads (frank-only: triage.py, overseer.py) ──────────────────────────
    def between(self, start: float, end: float) -> list[dict]:
        """All entries with start <= ts < end — the Overseer's own direct
        time-window query (spec: no subagent, to save context/$)."""
        out = []
        try:
            with self.path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if start <= entry.get("ts", 0) < end:
                        out.append(entry)
        except OSError:
            pass
        return out

    def since(self, ts: float) -> list[dict]:
        return self.between(ts, float("inf"))

    def prune(self, now: float | None = None) -> None:
        """Drop entries older than the retention window. Called on the daily
        reset tick (daemon.py), same cadence as the ledger/context reset —
        but this is its OWN retention policy, not the spec's context/ledger
        reset (see module docstring)."""
        now = time.time() if now is None else now
        cutoff = now - self.retention_seconds
        kept = self.between(cutoff, float("inf"))
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w") as fh:
            for entry in kept:
                fh.write(json.dumps(entry) + "\n")
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
