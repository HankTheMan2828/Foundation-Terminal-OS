"""Per-user high scores. Plain JSON under the account's own data dir — same
`FOUNDATIONHUB_DATA` root and `users/<name>/` layout the notes suite uses, so games
count toward the same quota'd space rather than inventing a second one.

Kept as plain functions over an explicit path so it's testable without any
notion of "the active user" — `active_username()`/`data_root()` figure that
out for the real program, tests pass in a tmp_path instead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_DATA",
                os.path.expanduser("~/.local/share/foundationhub")))


def active_username() -> str:
    """Whoever is logged into the Hub right now. Foundation Arcade is spawned
    as a child of the Hub (`Launch`), which sets FOUNDATIONHUB_USER in its own
    environment before exec'ing — inherited here. Falls back to the file the
    Hub publishes for the same purpose, then "guest" off-device."""
    name = os.environ.get("FOUNDATIONHUB_USER")
    if name:
        return name
    active_file = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER", "/run/foundationhub/active-user"))
    try:
        name = active_file.read_text().strip()
    except OSError:
        name = ""
    return name or "guest"


def scores_path(root: Path | None = None, username: str | None = None) -> Path:
    root = root if root is not None else data_root()
    username = username if username is not None else active_username()
    return root / "users" / username / "games" / "scores.json"


def load_scores(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def best_score(path: Path, game: str) -> int:
    return load_scores(path).get(game, 0)


def record_score(path: Path, game: str, score: int) -> int:
    """Update the best score for `game` if `score` beats it. Returns the
    (possibly unchanged) best score after recording."""
    scores = load_scores(path)
    best = scores.get(game, 0)
    if score <= best:
        return best
    scores[game] = score
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(scores, indent=1))
    os.replace(tmp, path)
    return score
