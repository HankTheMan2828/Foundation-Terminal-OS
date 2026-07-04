"""Reads the system-wide game records the in-house games write.

`games/foundation_arcade/scores.py` records ONE global entry per game to
`/var/lib/foundationhub/highscores.json`, and `games/foundation_chess/stats.py`
keeps one machine-wide win/loss/draw tally in `chess.json` alongside it —
never per user (operator correction 2026-07-04, applies to both). The Hub
and the games are separate distributions (see games/pyproject.toml), so
this is a small independent reader over the same on-disk formats, mirroring
how session.py reads Frank's ledger file directly rather than importing
frankd. Read-only: only the games write.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATE_DIR = Path(os.environ.get("FOUNDATIONHUB_STATE", "/var/lib/foundationhub"))


def scores_path() -> Path:
    return STATE_DIR / "highscores.json"


def chess_path() -> Path:
    return STATE_DIR / "chess.json"


def load_board(path: Path | None = None) -> dict[str, dict]:
    """{game: {"score": int, "name": str}} for the whole machine."""
    path = path if path is not None else scores_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict] = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        try:
            score = int(v.get("score", 0))
        except (TypeError, ValueError):
            continue
        out[str(k)] = {"score": score, "name": str(v.get("name") or "guest")}
    return out


def load_chess_record(path: Path | None = None) -> dict[str, int]:
    """{"wins": int, "losses": int, "draws": int}, machine-wide."""
    path = path if path is not None else chess_path()
    base = {"wins": 0, "losses": 0, "draws": 0}
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
