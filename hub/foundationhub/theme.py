"""CRT phosphor theme (spec §2): amber primary, green alt, scanlines, glow.

curses gives us a limited palette, so we degrade gracefully:
  * 256-color / can_change_color terminals  -> real amber (#FFB000) + phosphor green
  * 8-color terminals                        -> yellow/green approximations
Colors are chosen once at startup; screens ask for semantic pairs, not raw
color numbers, so a Settings > theme change is a one-place edit later.
"""
from __future__ import annotations

import curses

# Palette selection. Approved default: amber primary (docs/OPEN-QUESTIONS.md §7).
PALETTE_AMBER = "amber"
PALETTE_GREEN = "green"
_active_palette = PALETTE_AMBER

# Semantic color-pair ids.
PAIR_NORMAL = 1     # body text
PAIR_DIM = 2        # scanline / de-emphasized
PAIR_HILITE = 3     # selected menu row (inverse)
PAIR_ACCENT = 4     # titles / frame
PAIR_WARN = 5       # Frank status-bar warnings
PAIR_ALERT = 6      # Frank full-screen serious banner

# Custom color slots (only used when the terminal can redefine colors).
_C_PHOSPHOR = 16
_C_PHOSPHOR_DIM = 17
_C_ALERT = 18
_C_BG = 19


def set_palette(name: str) -> None:
    global _active_palette
    if name in (PALETTE_AMBER, PALETTE_GREEN):
        _active_palette = name


def get_palette() -> str:
    return _active_palette


def _rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    # curses wants 0..1000
    return (r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)


def init(stdscr) -> None:
    """Initialise color pairs for the active palette. Safe on mono terminals."""
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass

    fg = curses.COLOR_YELLOW if _active_palette == PALETTE_AMBER else curses.COLOR_GREEN
    dim = fg
    alert = curses.COLOR_RED
    bg = curses.COLOR_BLACK

    if curses.can_change_color() and curses.COLORS >= 256:
        if _active_palette == PALETTE_AMBER:
            curses.init_color(_C_PHOSPHOR, *_rgb(255, 176, 0))     # amber
            curses.init_color(_C_PHOSPHOR_DIM, *_rgb(140, 96, 0))
        else:
            curses.init_color(_C_PHOSPHOR, *_rgb(51, 255, 102))    # phosphor green
            curses.init_color(_C_PHOSPHOR_DIM, *_rgb(24, 130, 60))
        curses.init_color(_C_ALERT, *_rgb(255, 60, 40))
        curses.init_color(_C_BG, *_rgb(6, 6, 6))                   # near-black
        fg, dim, alert, bg = _C_PHOSPHOR, _C_PHOSPHOR_DIM, _C_ALERT, _C_BG

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
