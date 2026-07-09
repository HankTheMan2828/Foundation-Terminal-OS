"""CRT phosphor theme (spec §2): base yellow on near-black + a few warm accents.

The core look is one hue — base yellow, the same the installer and login screens
use. On top of that sit three retuned accent slots: a light amber for the top
banner text and bottom nav line, plus a cream-white and a soft-teal reserved for
games that need real contrast (chess pieces, 2048 tiles, tetris, sudoku givens).
curses gives us a limited palette, so screens ask for semantic pairs, not raw
color numbers; on mono terminals init() is a safe no-op.
"""
from __future__ import annotations

import curses

# Semantic color-pair ids.
PAIR_NORMAL = 1     # body text
PAIR_DIM = 2        # scanline / de-emphasized
PAIR_HILITE = 3     # selected menu row (inverse)
PAIR_ACCENT = 4     # frame / structural emphasis
PAIR_WARN = 5       # Frank status-bar warnings
PAIR_ALERT = 6      # Frank full-screen serious banner
PAIR_AMBER = 7      # top banner text + bottom nav line (light amber)
PAIR_BRIGHT = 8     # brightest phosphor highlight (games: light pieces, hot tiles)
PAIR_COOL = 9       # distinct cool accent, games only (never in core chrome)


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

    # Three accent hues share the base-yellow trick: the kernel VT
    # (foundationhub-session) and the kitty profile retune these otherwise-unused
    # palette slots to specific phosphor RGBs, so the 8-color names below land on
    # the intended colors. On a plain terminal that never got the retune they
    # degrade to stock green/cyan/white — still mutually distinct, which is all
    # the games need. Both the base slot AND its bold/bright twin are retuned, so
    # drawing these bold (banner titles, game pieces) stays on-hue.
    amber = curses.COLOR_GREEN      # slot 2  -> light amber
    cool = curses.COLOR_CYAN        # slot 6  -> soft teal (games only)
    bright = curses.COLOR_WHITE     # slot 7  -> cream white

    curses.init_pair(PAIR_NORMAL, fg, bg)
    curses.init_pair(PAIR_DIM, dim, bg)
    curses.init_pair(PAIR_HILITE, bg, fg)      # inverse = selected row "glow"
    curses.init_pair(PAIR_ACCENT, fg, bg)
    curses.init_pair(PAIR_WARN, alert, bg)
    curses.init_pair(PAIR_ALERT, curses.COLOR_WHITE, alert)
    curses.init_pair(PAIR_AMBER, amber, bg)
    curses.init_pair(PAIR_BRIGHT, bright, bg)
    curses.init_pair(PAIR_COOL, cool, bg)


def attr(pair: int, *, bold: bool = False, dim: bool = False) -> int:
    a = curses.color_pair(pair)
    if bold:
        a |= curses.A_BOLD
    if dim:
        a |= curses.A_DIM
    return a
