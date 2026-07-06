"""Recreation — games (spec §5). The title list is data, not code.

Reads /etc/foundationhub/recreation.toml so adding/removing a game is a config edit.
Ships a genre-organized default matching the spec's direction (roguelikes /
arcade / puzzle-strategy). The list follows the in-house mandate — see
docs/OPEN-QUESTIONS.md §2/§10: in-house games plus the two vendored Rogues.
"""
from __future__ import annotations

import curses

from .. import highscores, labels, theme
from ..app import MenuScreen, Screen, Launch
from ..ui import MenuItem
from ..session import ETC

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


class HighScoresScreen(Screen):
    """One system-wide record per game — never per user (operator correction
    2026-07-04, applies to the arcade's high scores AND chess's win/loss/draw
    tally alike). Read-only: the arcade board lists best score + who set it;
    chess has no single beatable score, so it gets its own machine-wide
    W/L/D line instead."""

    title = labels.HIGH_SCORES
    subtitle = "system-wide — one record per game, never per user"

    def __init__(self):
        self.board = highscores.load_board()
        self.chess_record = highscores.load_chess_record()

    def draw(self, win, top: int, left: int) -> None:
        h, w = win.getmaxyx()
        row = top
        if not self.board:
            win.addstr(row, left, labels.HIGH_SCORES_EMPTY,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
        else:
            name_col = max((len(game) for game in self.board), default=0) + 2
            for game in sorted(self.board):
                entry = self.board[game]
                try:
                    win.addstr(row, left, f"{game:<{name_col}}",
                               theme.attr(theme.PAIR_NORMAL, bold=True))
                    win.addstr(row, left + name_col,
                               f"{entry['score']:>8}   {entry['name']}"[: w - left - name_col - 2],
                               theme.attr(theme.PAIR_NORMAL))
                except curses.error:
                    pass
                row += 1

        row += 1
        try:
            win.addstr(row, left, f"{labels.HIGH_SCORES_CHESS:<10}",
                       theme.attr(theme.PAIR_NORMAL, bold=True))
            win.addstr(row, left + 10, labels.HIGH_SCORES_CHESS_FMT.format(
                w=self.chess_record["wins"], l=self.chess_record["losses"],
                d=self.chess_record["draws"]), theme.attr(theme.PAIR_NORMAL))
        except curses.error:
            pass

    def status_text(self) -> str:
        return labels.HINT_NAV


# Fallback list used off-device or before the config is installed.
# Each entry is a dict: {"name", "exec", optional "hint", optional "missing_hint"}.
# `hint` shows to the right of the row; `missing_hint` is what the Hub prints if
# the binary isn't installed (app.Launch) — used to mark the downloadable slot.
_DEFAULT = {
    # Roguelikes. The 1981 original (rogue3.6 -> "rogue") is the one vendored
    # game we ship (feedback #2: a real upstream binary, not an in-house build).
    #
    # "Rogue (1985)" is a DOWNLOADABLE skeleton, not shipped. The graphical
    # DOS/PC look the operator wants (docs/ROGUE-DOWNLOADABLE.md) has no
    # redistributable upstream we can bake into the ISO, so the slot is left as
    # a not-installed placeholder for a user-provided `rogue54` build. NetHack
    # was removed entirely (operator direction 2026-07-05). Dungeon Crawl was
    # dropped earlier — `crawl` was never in install/packages.txt.
    "roguelikes": [
        {"name": "Rogue (1981, OG)", "exec": ["rogue"]},
        {"name": "Rogue (1985)", "exec": ["rogue54"],
         "hint": "downloadable — not installed",
         "missing_hint": "[ downloadable graphical build — see docs/ROGUE-DOWNLOADABLE.md ]"},
    ],
    # One in-house program, five games (BUILD-QUEUE §5 item 1) — retires
    # nsnake, vitetris, ninvaders, 2048, and nudoku. Listed individually
    # (not nested under a "Foundation Arcade" sub-menu) per operator
    # request 2026-07-03 — each exec picks the game directly.
    "arcade": [
        {"name": "Snake", "exec": ["foundation-arcade", "snake"]},
        {"name": "Falling Blocks", "exec": ["foundation-arcade", "blocks"]},
        {"name": "2048", "exec": ["foundation-arcade", "2048"]},
        {"name": "Sudoku", "exec": ["foundation-arcade", "sudoku"]},
        {"name": "Invaders", "exec": ["foundation-arcade", "invaders"]},
    ],
    # Chess is in-house now (BUILD-QUEUE §5 item 2) — foundation-chess retires
    # gnuchess (vs. a built-in minimax AI).
    "puzzle / strategy": [
        {"name": "Chess", "exec": ["foundation-chess"]},
    ],
}


def _load():
    cfg = ETC / "recreation.toml"
    if tomllib and cfg.exists():
        try:
            data = tomllib.loads(cfg.read_text())
            out = {}
            for bucket, games in data.get("bucket", {}).items():
                out[bucket] = [dict(g) for g in games]
            if out:
                return out
        except Exception:
            pass
    return _DEFAULT


def _launch_action(game: dict):
    argv = game["exec"]
    missing = game.get("missing_hint", labels.NOT_INSTALLED)
    return lambda a: Launch(argv, missing_hint=missing)


def screen():
    items: list[MenuItem] = [
        MenuItem(labels.HIGH_SCORES, lambda a: HighScoresScreen(),
                 hint="system-wide, per game"),
    ]
    for bucket, games in _load().items():
        items.append(MenuItem("", enabled=False))  # gap above the section title
        items.append(MenuItem(f"— {bucket.upper()} —", enabled=False))
        items.append(MenuItem("", enabled=False))  # gap below the section title
        for game in games:
            items.append(MenuItem(game["name"],
                                  (lambda g: _launch_action(g))(game),
                                  hint=game.get("hint", "")))
    return MenuScreen(labels.RECREATION, items)
