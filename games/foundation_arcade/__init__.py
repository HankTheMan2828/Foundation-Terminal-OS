"""Foundation Arcade — one program, five in-house games (BUILD-QUEUE §5 item 1).

Retires the open-source stand-ins nsnake, vitetris, ninvaders, 2048, and
nudoku with a single terminal program: Snake, a falling-blocks game, 2048,
Sudoku, and an Invaders-like, sharing one game loop, input map, CRT chrome,
and per-user score file.

Pure stdlib + curses, same portability constraint as the Hub. `foundationhub` is an
optional import (CRT chrome reuse) with a graceful local fallback — this
program must still run standalone if foundationhub isn't on the path.
"""
from __future__ import annotations

__version__ = "0.1.1"
