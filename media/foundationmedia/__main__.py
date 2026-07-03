"""Entry point: ``python -m foundationmedia`` (installed as the
`foundationmedia` console script, launched by the Hub's Programs screen via
`Launch(["foundationmedia"])`).

Any unhandled error restores the terminal before exiting — this program is
spawned as a child of the Hub's login-shell session, so it must never leave
the terminal in a broken state (same rule as foundationhub's own __main__).
"""
from __future__ import annotations

import curses
import sys

from . import labels, library
from .tui import MediaTUI


def _main(stdscr) -> None:
    curses.set_escdelay(25)  # default ~1000ms made Esc feel laggy vs. Backspace
    h, w = stdscr.getmaxyx()
    if h < 16 or w < 50:
        stdscr.erase()
        try:
            stdscr.addstr(0, 0, labels.NOT_A_TERMINAL)
        except curses.error:
            pass
        stdscr.refresh()
        stdscr.getch()
        return
    root = library.media_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)   # first run: empty library
    except OSError:
        pass    # read-only/odd dev setups still get the (empty) UI
    MediaTUI(root).run(stdscr)


def main() -> int:
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # never leave a half-drawn screen behind
        sys.stderr.write(f"foundationmedia exited: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
