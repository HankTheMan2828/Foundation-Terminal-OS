"""`python -m foundation_chess` — launched by the Hub's Recreation screen via
the `foundation-chess` bin shim (Launch(["foundation-chess"]))."""
from __future__ import annotations

import curses

from . import game


def main() -> None:
    curses.wrapper(game.main)


if __name__ == "__main__":
    main()
