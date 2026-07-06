"""Per-user violation COUNTS — the one number Frank discloses per person.

A "violation" is a finding that produced a user-facing reaction (WARN or
LOCKOUT). Silent observations don't count. The store keeps one integer per
username, persisted so the record survives reboots and the daily reset alike —
records follow the person (docs/USERS.md).

Disclosure philosophy (spec §6): this is a COUNT and nothing else — when and
how many, never why. The login roster shows it next to each account via
lockstate.write_public; the detail behind each increment stays in the
frank-only incidents store. Like the ledger/incidents split, this module never
touches either of those files, so the boundary can't blur.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class ViolationCounts:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.counts: dict[str, int] = {}
        try:
            data = json.loads(self.path.read_text())
            self.counts = {str(k): int(v) for k, v in data.items()}
        except (OSError, ValueError, TypeError, AttributeError):
            self.counts = {}   # first boot / corrupt file: start clean

    def increment(self, user: str) -> None:
        self.counts[user] = self.counts.get(user, 0) + 1
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.counts))
            os.replace(tmp, self.path)   # atomic, like lockstate
        except OSError:
            pass   # off-device: /var/lib/frank may not exist; counts stay in-memory
