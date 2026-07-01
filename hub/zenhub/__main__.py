"""Entry point: ``python -m zenhub``.

Because the Hub is the login shell (spec §4), this must be robust: any unhandled
error should restore the terminal and exit cleanly (which logs the session out)
rather than leaving a broken screen or — worse — dropping to a shell.
"""
from __future__ import annotations

import curses
import sys

from . import theme
from .app import App
from .screens import build_home


def _main(stdscr) -> None:
    theme.init(stdscr)
    App(stdscr, build_home).run()


def main() -> int:
    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # never leave a half-drawn screen on the login shell
        sys.stderr.write(f"zenhub exited: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
