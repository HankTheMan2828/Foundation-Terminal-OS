"""Entry point: ``python -m foundation_arcade`` (installed as the
`foundation-arcade` console script). The Hub's Recreation screen lists each
cabinet game directly (no separate "Foundation Arcade" sub-menu — operator
request 2026-07-03), launching one via
`Launch(["foundation-arcade", "<game-id>"])`. Running with no argument still
shows the old cabinet-style menu, kept for direct terminal use.

Any unhandled error restores the terminal before exiting — this program is
spawned as a child of the Hub's login-shell session, so it must never leave
the terminal in a broken state (same rule as foundationhub's own __main__).
"""
from __future__ import annotations

import curses
import sys

from . import chrome, engine, labels
from . import snake, blocks, game2048, sudoku, invaders

_GAMES = [
    ("snake", labels.GAME_SNAKE, snake.run),
    ("blocks", labels.GAME_BLOCKS, blocks.run),
    ("2048", labels.GAME_2048, game2048.run),
    ("sudoku", labels.GAME_SUDOKU, sudoku.run),
    ("invaders", labels.GAME_INVADERS, invaders.run),
]
_GAMES_BY_ID = {game_id: run for game_id, _, run in _GAMES}


def _menu(stdscr) -> None:
    index = 0

    while True:
        top, left = chrome.draw_chrome(stdscr, labels.ARCADE_TITLE, labels.ARCADE_TAGLINE)
        for i, (_, name, _) in enumerate(_GAMES):
            selected = i == index
            a = chrome.attr(chrome.PAIR_HILITE if selected else chrome.PAIR_NORMAL,
                            bold=selected)
            marker = "> " if selected else "  "
            try:
                stdscr.addstr(top + i, left, f"{marker}{name}", a)
            except curses.error:
                pass
        chrome.draw_statusbar(stdscr, labels.ARCADE_HINT_MENU)
        stdscr.noutrefresh()
        curses.doupdate()

        key = stdscr.getch()
        if key in engine.KEYS_QUIT:
            return
        if key in engine.KEYS_UP:
            index = (index - 1) % len(_GAMES)
        elif key in engine.KEYS_DOWN:
            index = (index + 1) % len(_GAMES)
        elif key in engine.KEYS_ACTION:
            _play(stdscr, _GAMES[index][2])


def _play(stdscr, game_run) -> None:
    h, w = stdscr.getmaxyx()
    if h < 22 or w < 40:
        stdscr.erase()
        try:
            stdscr.addstr(0, 0, labels.NOT_A_TERMINAL)
        except curses.error:
            pass
        stdscr.refresh()
        stdscr.nodelay(False)
        stdscr.getch()
        return
    game_run(stdscr)


def _main(stdscr, game_run) -> None:
    curses.set_escdelay(25)  # default ~1000ms made Esc feel laggy vs. Backspace
    chrome.init(stdscr)
    curses.curs_set(0)
    stdscr.keypad(True)
    if game_run is None:
        _menu(stdscr)
    else:
        _play(stdscr, game_run)


def main() -> int:
    game_id = sys.argv[1] if len(sys.argv) > 1 else None
    if game_id is not None and game_id not in _GAMES_BY_ID:
        sys.stderr.write(f"foundation-arcade: unknown game {game_id!r}\n")
        return 1
    game_run = _GAMES_BY_ID.get(game_id) if game_id else None
    try:
        curses.wrapper(_main, game_run)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # never leave a half-drawn screen behind
        sys.stderr.write(f"foundation-arcade exited: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
