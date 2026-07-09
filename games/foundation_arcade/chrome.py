"""CRT chrome, reused rather than duplicated.

Foundation Arcade is a standalone program (Hybrid model: games are separate
in-house programs, not Hub screens), but it shares the same terminal and the
same operator, so it borrows the Hub's amber/green bezel instead of drawing
its own. `foundationhub` is optional: if it isn't importable (this program run from
a bare checkout with no sibling `hub/` on the path), fall back to a minimal
local bezel so the arcade still runs on its own.
"""
from __future__ import annotations

import curses
import sys
from pathlib import Path


def _import_foundationhub():
    try:
        import foundationhub.theme as theme
        import foundationhub.ui as ui
        return theme, ui
    except ImportError:
        pass
    # Dev/repo layout: games/ and hub/ are sibling top-level dirs.
    hub_dir = Path(__file__).resolve().parents[2] / "hub"
    if hub_dir.is_dir() and str(hub_dir) not in sys.path:
        sys.path.insert(0, str(hub_dir))
    try:
        import foundationhub.theme as theme
        import foundationhub.ui as ui
        return theme, ui
    except ImportError:
        return None, None


_theme, _ui = _import_foundationhub()

PAIR_NORMAL, PAIR_DIM, PAIR_HILITE, PAIR_ACCENT, PAIR_WARN, PAIR_ALERT = range(1, 7)
# Accent pairs (see foundationhub.theme): amber banner/nav, plus cream + teal for
# game contrast. Ids match the Hub so `attr()` delegates cleanly when it's present.
PAIR_AMBER, PAIR_BRIGHT, PAIR_COOL = 7, 8, 9


def init(stdscr) -> None:
    if _theme is not None:
        _theme.init(stdscr)
        return
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        pass
    curses.init_pair(PAIR_NORMAL, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(PAIR_DIM, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(PAIR_HILITE, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(PAIR_ACCENT, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(PAIR_WARN, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(PAIR_ALERT, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(PAIR_AMBER, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(PAIR_BRIGHT, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(PAIR_COOL, curses.COLOR_CYAN, curses.COLOR_BLACK)


def attr(pair: int, *, bold: bool = False, dim: bool = False) -> int:
    if _theme is not None:
        return _theme.attr(pair, bold=bold, dim=dim)
    a = curses.color_pair(pair)
    if bold:
        a |= curses.A_BOLD
    if dim:
        a |= curses.A_DIM
    return a


def draw_chrome(win, title: str, subtitle: str = "") -> tuple[int, int]:
    if _ui is not None:
        return _ui.draw_chrome(win, title, subtitle)
    win.erase()
    h, w = win.getmaxyx()
    try:
        win.attron(attr(PAIR_ACCENT))
        win.border()
        win.attroff(attr(PAIR_ACCENT))
        _center(win, 1, title, attr(PAIR_ACCENT, bold=True))
        if subtitle:
            _center(win, 2, subtitle, attr(PAIR_DIM, dim=True))
        win.hline(3, 1, curses.ACS_HLINE, w - 2)
    except curses.error:
        pass
    return (5, 4)


def draw_playfield(win, top: int, left: int, height: int, width: int) -> tuple[int, int]:
    """Center a `height` x `width` playfield inside the chrome's content area
    and draw a border around it (feedback: games were corner-anchored and
    borderless on large consoles). Returns the interior (top, left); games
    keep drawing cells exactly as before, just from this recentered origin."""
    h, w = win.getmaxyx()
    avail_h = max(0, (h - 3) - top)
    avail_w = max(0, (w - 1) - left)
    box_h, box_w = height + 2, width + 2
    box_top = top + max(0, (avail_h - box_h) // 2)
    box_left = left + max(0, (avail_w - box_w) // 2)
    a = attr(PAIR_ACCENT)
    try:
        win.attron(a)
        try:
            win.hline(box_top, box_left, curses.ACS_HLINE, box_w)
            win.hline(box_top + box_h - 1, box_left, curses.ACS_HLINE, box_w)
            win.vline(box_top, box_left, curses.ACS_VLINE, box_h)
            win.vline(box_top, box_left + box_w - 1, curses.ACS_VLINE, box_h)
            win.addch(box_top, box_left, curses.ACS_ULCORNER)
            win.addch(box_top, box_left + box_w - 1, curses.ACS_URCORNER)
            win.addch(box_top + box_h - 1, box_left, curses.ACS_LLCORNER)
            win.addch(box_top + box_h - 1, box_left + box_w - 1, curses.ACS_LRCORNER)
        except curses.error:
            pass
    finally:
        win.attroff(a)
    return box_top + 1, box_left + 1


def draw_statusbar(win, text: str, *, warn: bool = False) -> None:
    if _ui is not None:
        _ui.draw_statusbar(win, text, warn=warn)
        return
    h, w = win.getmaxyx()
    pair = PAIR_WARN if warn else PAIR_DIM
    try:
        win.addstr(h - 2, 2, text[: w - 4].ljust(w - 4), attr(pair, bold=warn, dim=not warn))
    except curses.error:
        pass


def _center(win, y: int, text: str, a: int) -> None:
    h, w = win.getmaxyx()
    x = max(1, (w - len(text)) // 2)
    try:
        win.addstr(y, x, text[: w - 2], a)
    except curses.error:
        pass
