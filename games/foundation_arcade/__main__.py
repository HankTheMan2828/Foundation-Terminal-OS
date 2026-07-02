"""Entry point: ``python -m foundation_arcade`` (installed as the
`foundation-arcade` console script, launched by the Hub's Recreation screen
via `Launch(["foundation-arcade"])`).

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
    (labels.GAME_SNAKE, snake.run),
    (labels.GAME_BLOCKS, blocks.run),
    (labels.GAME_2048, game2048.run),
    (labels.GAME_SUDOKU, sudoku.run),
    (labels.GAME_INVADERS, invaders.run),
]


def _menu(stdscr) -> None:
    chrome.init(stdscr)
    curses.curs_set(0)
    stdscr.keypad(True)
    index = 0

    while True:
        top, left = chrome.draw_chrome(stdscr, labels.ARCADE_TITLE, labels.ARCADE_TAGLINE)
        for i, (name, _) in enumerate(_GAMES):
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
            _play(stdscr, _GAMES[index][1])


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


def _main(stdscr) -> None:
    _menu(stdscr)


def main() -> int:
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # never leave a half-drawn screen behind
        sys.stderr.write(f"foundation-arcade exited: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
