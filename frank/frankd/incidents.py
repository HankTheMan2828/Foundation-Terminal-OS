"""The frank-only detail store (spec §6).

Holds the FULL detail of every finding — what was flagged, why, the matched
content, the AI commentary. This is the opposite of the visible ledger: it is
never surfaced to any user through any interface. File is frank:frank 0600.

Separate from ledger.py on purpose. The ledger holds timestamps only; this holds
everything. The two are never merged in code so the boundary can't be blurred by
accident.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .model import Finding


class IncidentStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 0600 — owner (frank) only. Enforced again by install/05-frank.sh.
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def record(self, finding: Finding, reaction_kind: str, commentary: str,
               now: float | None = None) -> None:
        """Append full detail. NEVER read back into any user-facing surface."""
        entry = {
            "ts": time.time() if now is None else now,
            "user": finding.event.user,      # records follow the person (docs/USERS.md)
            "rule_id": finding.rule_id,
            "track": finding.track.value,
            "severity": finding.severity.name,
            "source": finding.event.source.value,
            "matched": finding.matched,          # content — frank-only
            "event_text": finding.event.text,    # content — frank-only
            "description": finding.description,
            "reaction": reaction_kind,
            "commentary": commentary,
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

    # ── reads (frank-only consumers: triage.py, overseer.py) ────────────────
    # These never feed any user-facing surface — only the sifting/overseer AI
    # tiers, which are themselves frank-internal (see ARCHITECTURE.md).
    def between(self, start: float, end: float) -> list[dict]:
        """All entries with start <= ts < end. Used by the Overseer to sift a
        specific time window itself (spec: no subagent, to save context/$)."""
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
        """All entries newer than ts. Used by triage.py's periodic scan."""
        return self.between(ts, float("inf"))
