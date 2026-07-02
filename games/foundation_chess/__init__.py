"""Foundation Chess — in-house chess vs. a built-in AI (BUILD-QUEUE §5 item 2).

Retires the open-source stand-in gnuchess with a standalone terminal program:
a pure-stdlib rules engine (`board.py`), a small minimax + piece-square AI
(`ai.py`), and a curses front-end (`game.py`) in the shared CRT register.

Pure stdlib + curses, same portability constraint as the Hub. `foundationhub` is an
optional import (CRT chrome reuse) with a graceful local fallback — this
program must still run standalone if foundationhub isn't on the path.
"""
from __future__ import annotations

__version__ = "0.1.0"
