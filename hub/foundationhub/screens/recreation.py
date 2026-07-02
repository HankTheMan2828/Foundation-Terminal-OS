"""Recreation — games (spec §5). The title list is data, not code.

Reads /etc/foundationhub/recreation.toml so adding/removing a game is a config edit.
Ships a genre-organized default matching the spec's direction (roguelikes /
arcade / puzzle-strategy). The list follows the in-house mandate — see
docs/OPEN-QUESTIONS.md §2/§10: in-house games plus interim NetHack.
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
    # NetHack is the interim stand-in until the in-house roguelikes land
    # (docs/ROGUELIKE-DESIGN.md). Dungeon Crawl was dropped — `crawl` was
    # never in install/packages.txt, so it was a dead entry on target.
    "roguelikes": [
        ("NetHack", ["nethack"]),
    ],
    # One in-house program, five games (BUILD-QUEUE §5 item 1) — retires
    # nsnake, vitetris, ninvaders, 2048, and nudoku.
    "arcade": [
        ("Foundation Arcade", ["foundation-arcade"]),
    ],
    # Chess is in-house now (BUILD-QUEUE §5 item 2) — foundation-chess retires
    # gnuchess (vs. a built-in minimax AI).
    "puzzle / strategy": [
        ("Chess", ["foundation-chess"]),
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
        items.append(MenuItem("", enabled=False))  # gap above the section title
        items.append(MenuItem(f"— {bucket.upper()} —", enabled=False))
        items.append(MenuItem("", enabled=False))  # gap below the section title
        for name, argv in games:
            items.append(MenuItem(name, (lambda av: (lambda a: Launch(av)))(argv)))
    return MenuScreen(labels.RECREATION, items)
