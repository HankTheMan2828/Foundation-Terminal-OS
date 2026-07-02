"""Shared engine: frame timing + the one input map every game uses.

No curses window handling lives here beyond `curses` key constants — keeping
the timing/input logic separate from drawing is what makes it unit-testable
(see tests/test_engine.py).
"""
from __future__ import annotations

import curses
import time

# One input map for the whole cabinet: arrows, WASD, and vim hjkl all agree,
# so whichever the operator reaches for first works everywhere.
KEYS_LEFT = {curses.KEY_LEFT, ord("a"), ord("A"), ord("h")}
KEYS_RIGHT = {curses.KEY_RIGHT, ord("d"), ord("D"), ord("l")}
KEYS_UP = {curses.KEY_UP, ord("w"), ord("W"), ord("k")}
KEYS_DOWN = {curses.KEY_DOWN, ord("s"), ord("S"), ord("j")}
KEYS_ACTION = {ord(" "), curses.KEY_ENTER, ord("\n"), ord("\r")}
KEYS_PAUSE = {ord("p"), ord("P")}
KEYS_QUIT = {27, ord("q"), ord("Q")}

DIR_UP = (-1, 0)
DIR_DOWN = (1, 0)
DIR_LEFT = (0, -1)
DIR_RIGHT = (0, 1)


def direction_for(key: int):
    """Map a keycode to a (drow, dcol) direction, or None."""
    if key in KEYS_UP:
        return DIR_UP
    if key in KEYS_DOWN:
        return DIR_DOWN
    if key in KEYS_LEFT:
        return DIR_LEFT
    if key in KEYS_RIGHT:
        return DIR_RIGHT
    return None


class Clock:
    """Wall-clock accumulator so a game's gravity/step rate is independent of
    how often the input-poll loop wakes up. `curses` gives us polling, not a
    frame callback, so each game asks the clock how many milliseconds have
    passed and advances its own accumulator against a fixed step."""

    def __init__(self):
        self._last = time.monotonic()

    def elapsed_ms(self) -> int:
        now = time.monotonic()
        dt = int((now - self._last) * 1000)
        self._last = now
        return max(0, dt)


class StepAccumulator:
    """Ticks a fixed-size step out of variable elapsed_ms() calls. Used for
    gravity in Falling Blocks, the snake tick, invader marches, etc."""

    def __init__(self, step_ms: int):
        self.step_ms = step_ms
        self._acc = 0

    def advance(self, dt_ms: int) -> int:
        """Add dt_ms; return how many whole steps have now elapsed."""
        self._acc += dt_ms
        steps = self._acc // self.step_ms
        self._acc -= steps * self.step_ms
        return steps

    def set_step_ms(self, step_ms: int) -> None:
        self.step_ms = max(1, step_ms)
