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


# ── kernel-VT palette control (full-color launches) ──────────────────────────
# foundationhub-session retunes the VT's global 16-color palette to phosphor
# hues at login (\e]PXRRGGBB — a kernel-console feature). That palette is
# GLOBAL: a launched game inherits it, so its greens/yellows/whites all render
# as phosphor amber. A game flagged full_color (Rogue 5.4's DOS-style colors)
# needs the stock palette while it runs and the phosphor one back afterwards.
# These strings mirror system/usr/local/bin/foundationhub-session — keep in sync.

_VT_THEME_SEQ = {
    PALETTE_GREEN: "\x1b]P00a0a0a\x1b]P1ff5030\x1b]P233ff66\x1b]P333ff66"
                   "\x1b]P77cff9c\x1b]P810361c",
    PALETTE_AMBER: "\x1b]P00a0a0a\x1b]P1ff5030\x1b]P2ffb000\x1b]P3ffb000"
                   "\x1b]P7ffd060\x1b]P83a2a00",
}
_VT_PALETTE_RESET = "\x1b]R"    # linux console: reset palette to the stock one


def _on_kernel_vt() -> bool:
    import os
    # \e]P / \e]R are linux-console specials; on other terminals they start an
    # OSC that can swallow output. Only ever emit them on the kernel VT.
    return os.environ.get("TERM") == "linux"


def _emit(seq: str) -> None:
    import sys
    try:
        sys.stdout.write(seq)
        sys.stdout.flush()
    except OSError:
        pass


def vt_stock_palette() -> None:
    """Restore the kernel VT's stock palette (true colors) for a launch."""
    if _on_kernel_vt():
        _emit(_VT_PALETTE_RESET)


def vt_theme_palette() -> None:
    """Re-apply the phosphor palette after a full-color launch returns."""
    if _on_kernel_vt():
        _emit(_VT_THEME_SEQ[_active_palette])
