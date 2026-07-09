"""CRT phosphor theme (spec §2): a single fixed yellow palette, scanlines, glow.

There is one look — base yellow on near-black, the same hue the installer and
login screens use. curses gives us a limited palette, so screens ask for
semantic pairs, not raw color numbers; on mono terminals init() is a safe no-op.
"""
from __future__ import annotations

import curses

# Semantic color-pair ids.
PAIR_NORMAL = 1     # body text
PAIR_DIM = 2        # scanline / de-emphasized
PAIR_HILITE = 3     # selected menu row (inverse)
PAIR_ACCENT = 4     # titles / frame
PAIR_WARN = 5       # Frank status-bar warnings
PAIR_ALERT = 6      # Frank full-screen serious banner


def init(stdscr) -> None:
    """Initialise color pairs for the yellow palette. Safe on mono terminals."""
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass

    # Stock terminal yellow — the OS's one and only phosphor hue. The kernel VT
    # (foundationhub-session) retunes its yellow slot to base yellow, so this
    # lands on the same color the installer/login screens show. Scanline
    # dimming comes from the A_DIM attribute, not a separate hue.
    fg = curses.COLOR_YELLOW
    dim = fg
    alert = curses.COLOR_RED
    bg = curses.COLOR_BLACK

    curses.init_pair(PAIR_NORMAL, fg, bg)
    curses.init_pair(PAIR_DIM, dim, bg)
    curses.init_pair(PAIR_HILITE, bg, fg)      # inverse = selected row "glow"
    curses.init_pair(PAIR_ACCENT, fg, bg)
    curses.init_pair(PAIR_WARN, alert, bg)
    curses.init_pair(PAIR_ALERT, curses.COLOR_WHITE, alert)


def attr(pair: int, *, bold: bool = False, dim: bool = False) -> int:
    a = curses.color_pair(pair)
    if bold:
        a |= curses.A_BOLD
    if dim:
        a |= curses.A_DIM
    return a
