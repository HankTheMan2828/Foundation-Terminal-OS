"""Recreation — games (spec §5). The title list is data, not code.

Reads /etc/zenhub/recreation.toml so adding/removing a game is a config edit.
Ships a genre-organized default matching the spec's direction (roguelikes /
arcade / puzzle-strategy). Final list is [TODO(approval)] — see
docs/OPEN-QUESTIONS.md §2.
"""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen, Launch
from ..ui import MenuItem
from ..session import ETC

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

# Fallback list used off-device or before the config is installed.
_DEFAULT = {
    "roguelikes": [
        ("NetHack", ["nethack"]),
        ("Dungeon Crawl", ["crawl"]),
    ],
    "arcade": [
        ("Snake", ["nsnake"]),
        ("Tetris", ["vitetris"]),
        ("Invaders", ["ninvaders"]),
    ],
    "puzzle / strategy": [
        ("Chess", ["gnuchess"]),
        ("2048", ["2048"]),
        ("Sudoku", ["nudoku"]),
    ],
}


def _load():
    cfg = ETC / "recreation.toml"
    if tomllib and cfg.exists():
        try:
            data = tomllib.loads(cfg.read_text())
            out = {}
            for bucket, games in data.get("bucket", {}).items():
                out[bucket] = [(g["name"], g["exec"]) for g in games]
            if out:
                return out
        except Exception:
            pass
    return _DEFAULT


def screen():
    items: list[MenuItem] = []
    for bucket, games in _load().items():
        items.append(MenuItem(f"— {bucket.upper()} —", enabled=False))
        for name, argv in games:
            items.append(MenuItem(name, (lambda av: (lambda a: Launch(av)))(argv),
                                  hint=argv[0]))
    return MenuScreen(labels.RECREATION, items)
