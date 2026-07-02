"""Per-user win/loss/draw record. Plain JSON under the account's own data dir —
same `FOUNDATIONHUB_DATA` root and `users/<name>/games/` layout the arcade's scores
use, so chess counts toward the same quota'd space rather than inventing a
second one (GLOBAL CONSTRAINTS: all user data is per-account, storage is quota'd).

Kept as plain functions over an explicit path so it's testable without any
notion of "the active user" — `active_username()`/`data_root()` figure that out
for the real program; tests pass in a tmp_path instead. Mirrors
games/foundation_arcade/scores.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# The three outcomes we tally, from the operator's perspective.
WIN, LOSS, DRAW = "wins", "losses", "draws"


def data_root() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_DATA",
                os.path.expanduser("~/.local/share/foundationhub")))


def active_username() -> str:
    """Whoever is logged into the Hub right now. Foundation Chess is spawned as
    a child of the Hub (`Launch`), which sets FOUNDATIONHUB_USER in its environment
    before exec'ing — inherited here. Falls back to the file the Hub publishes
    for the same purpose, then "guest" off-device."""
    name = os.environ.get("FOUNDATIONHUB_USER")
    if name:
        return name
    active_file = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER", "/run/foundationhub/active-user"))
    try:
        name = active_file.read_text().strip()
    except OSError:
        name = ""
    return name or "guest"


def stats_path(root: Path | None = None, username: str | None = None) -> Path:
    root = root if root is not None else data_root()
    username = username if username is not None else active_username()
    return root / "users" / username / "games" / "chess.json"


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
    """Increment the tally for `outcome` (WIN/LOSS/DRAW) and persist. Returns
    the updated record. An unknown outcome is a no-op (still returns current)."""
    rec = load_record(path)
    if outcome in rec:
        rec[outcome] += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1))
        os.replace(tmp, path)
    return rec
