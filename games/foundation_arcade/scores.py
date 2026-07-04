"""High scores — ONE system-wide board per game, for the whole machine.

Operator correction (2026-07-04): scoring is system-wide ONLY, never per
user — no per-user score lists, no per-user filtering, no per-user storage.
There is exactly one file, one entry per game. Each entry still records the
name of whoever set it (so the board reads like an arcade cabinet — score +
who), but that's attribution on a shared record, not per-account storage.

Stored under `/var/lib/foundationhub` — outside any account's quota'd data
space (`~/.local/share/foundationhub/users/<name>/...`), so scores never
show up in a user's file/folder area. The Home Hub's Recreation screen reads
this same file to show the board (see `hub/foundationhub/highscores.py`).

Kept as plain functions over an explicit path so it's testable without any
notion of "the active user" — `active_username()`/`state_dir()` figure that
out for the real program, tests pass in a tmp_path instead.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def state_dir() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_STATE", "/var/lib/foundationhub"))


def active_username() -> str:
    """Whoever is logged into the Hub right now. Foundation Arcade is spawned
    as a child of the Hub (`Launch`), which sets FOUNDATIONHUB_USER in its own
    environment before exec'ing — inherited here. Falls back to the file the
    Hub publishes for the same purpose, then "guest" off-device.

    Used only to *attribute* a high score to a name — never to select or
    filter which scores are visible."""
    name = os.environ.get("FOUNDATIONHUB_USER")
    if name:
        return name
    active_file = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER", "/run/foundationhub/active-user"))
    try:
        name = active_file.read_text().strip()
    except OSError:
        name = ""
    return name or "guest"


def scores_path(root: Path | None = None) -> Path:
    root = root if root is not None else state_dir()
    return root / "highscores.json"


def load_scores(path: Path) -> dict[str, dict]:
    """{game: {"score": int, "name": str}} for the whole machine."""
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


def best_score(path: Path, game: str) -> int:
    entry = load_scores(path).get(game)
    return entry["score"] if entry else 0


def best_entry(path: Path, game: str) -> dict | None:
    """{"score": int, "name": str} for `game`, or None if no score is on record."""
    return load_scores(path).get(game)


def record_score(path: Path, game: str, score: int, name: str | None = None) -> int:
    """Update the system-wide best for `game` if `score` beats it, attributing
    it to `name` (defaults to the active user). Returns the (possibly
    unchanged) best score after recording."""
    scores = load_scores(path)
    best = scores.get(game, {}).get("score", 0)
    if score <= best:
        return best
    scores[game] = {"score": score, "name": name or active_username()}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(scores, indent=1))
    os.replace(tmp, path)
    return score
