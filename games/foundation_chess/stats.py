"""Machine-wide win/loss/draw record — ONE system-wide tally, not per user
(operator correction 2026-07-04: no per-user score/record lists, no
per-user filtering, ever — applies to chess same as the arcade's high
scores). Stored under `/var/lib/foundationhub`, the same machine-wide state
dir `games/foundation_arcade/scores.py` uses — outside any account's
quota'd `~/.local/share/foundationhub` data space, so it never shows up in
a user's file/folder area.

Kept as plain functions over an explicit path so it's testable without any
notion of "the active user" — tests pass in a tmp_path instead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# The three outcomes we tally, from the operator's perspective.
WIN, LOSS, DRAW = "wins", "losses", "draws"


def state_dir() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_STATE", "/var/lib/foundationhub"))


def stats_path(root: Path | None = None) -> Path:
    root = root if root is not None else state_dir()
    return root / "chess.json"


def load_record(path: Path) -> dict[str, int]:
    base = {WIN: 0, LOSS: 0, DRAW: 0}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return base
    if not isinstance(data, dict):
        return base
    for k in base:
        try:
            base[k] = int(data.get(k, 0))
        except (TypeError, ValueError):
            base[k] = 0
    return base


def record_result(path: Path, outcome: str) -> dict[str, int]:
    """Increment the machine-wide tally for `outcome` (WIN/LOSS/DRAW) and
    persist. Returns the updated record. An unknown outcome is a no-op
    (still returns current)."""
    rec = load_record(path)
    if outcome in rec:
        rec[outcome] += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1))
        os.replace(tmp, path)
    return rec
