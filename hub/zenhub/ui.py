"""Reusable curses widgets: CRT chrome, the highlight-and-Enter Menu, banners.

Kept deliberately small and dependency-free. Screens compose these; they don't
draw raw curses primitives themselves.
"""
from __future__ import annotations

import curses
from typing import Callable, Optional

from . import theme
from . import labels

# Vim + arrow navigation (spec §4).
KEYS_UP = {curses.KEY_UP, ord("k")}
KEYS_DOWN = {curses.KEY_DOWN, ord("j")}
KEYS_SELECT = {curses.KEY_ENTER, ord("\n"), ord("\r"), ord(" ")}
KEYS_BACK = {27, curses.KEY_BACKSPACE, 127, 8, ord("h")}  # Esc / Backspace / h


def draw_chrome(win, title: str, subtitle: str = "", *, scanlines: bool = True) -> tuple[int, int]:
    """Draw the CRT bezel + title bar. Returns the (top, left) of the content box."""
    win.erase()
    h, w = win.getmaxyx()

    # Faint scanlines: dim the background on alternate rows for the phosphor look.
    if scanlines:
        for y in range(h):
            if y % 2 == 1:
                try:
                    win.addstr(y, 0, " " * (w - 1), theme.attr(theme.PAIR_DIM, dim=True))
                except curses.error:
                    pass

    # Outer frame.
    try:
        win.attron(theme.attr(theme.PAIR_ACCENT))
        win.border()
        win.attroff(theme.attr(theme.PAIR_ACCENT))
    except curses.error:
        pass

    # Title bar.
    _center(win, 1, title, theme.attr(theme.PAIR_ACCENT, bold=True))
    if subtitle:
        _center(win, 2, subtitle, theme.attr(theme.PAIR_DIM, dim=True))
    try:
        win.hline(3, 2, curses.ACS_HLINE, w - 4, )
    except curses.error:
        pass
    return (5, 4)


def draw_statusbar(win, text: str, *, warn: bool = False) -> None:
    """Bottom status line. Frank's normal warnings surface here (spec §6)."""
    h, w = win.getmaxyx()
    pair = theme.PAIR_WARN if warn else theme.PAIR_DIM
    try:
        win.addstr(h - 2, 2, text[: w - 4].ljust(w - 4),
                   theme.attr(pair, bold=warn, dim=not warn))
    except curses.error:
        pass


def _center(win, y: int, text: str, attr: int) -> None:
    h, w = win.getmaxyx()
    x = max(1, (w - len(text)) // 2)
    try:
        win.addstr(y, x, text[: w - 2], attr)
    except curses.error:
        pass


class MenuItem:
    """One selectable row. `action` gets the App; return value drives navigation."""

    def __init__(self, label: str, action: Optional[Callable] = None,
                 *, hint: str = "", enabled: bool = True):
        self.label = label
        self.action = action
        self.hint = hint
        self.enabled = enabled


class Menu:
    """Highlight + Enter list. Arrow or vim keys move; Enter fires `action`."""

    def __init__(self, items: list[MenuItem]):
        self.items = items
        self.index = 0

    def move(self, delta: int) -> None:
        n = len(self.items)
        if not n:
            return
        for _ in range(n):
            self.index = (self.index + delta) % n
            if self.items[self.index].enabled:
                return

    def handle_key(self, key: int, app):
        if key in KEYS_UP:
            self.move(-1)
        elif key in KEYS_DOWN:
            self.move(+1)
        elif key in KEYS_SELECT:
            item = self.current
            if item and item.enabled and item.action:
                return item.action(app)
        return None

    @property
    def current(self) -> Optional[MenuItem]:
        return self.items[self.index] if self.items else None

    def draw(self, win, top: int, left: int) -> None:
        h, w = win.getmaxyx()
        for row, item in enumerate(self.items):
            y = top + row
            if y >= h - 2:
                break
            selected = row == self.index
            if not item.enabled:
                a = theme.attr(theme.PAIR_DIM, dim=True)
                marker = "  "
            elif selected:
                a = theme.attr(theme.PAIR_HILITE, bold=True)
                marker = "▶ "
            else:
                a = theme.attr(theme.PAIR_NORMAL)
                marker = "  "
            text = f"{marker}{item.label}"
            if item.hint:
                text = f"{text}".ljust(28) + item.hint
            try:
                win.addstr(y, left, text[: w - left - 2].ljust(min(40, w - left - 2)), a)
            except curses.error:
                pass


def full_screen_banner(win, lines: list[str], *, alert: bool = True) -> None:
    """Serious-severity interrupting banner (spec §6). Fills the screen."""
    win.erase()
    h, w = win.getmaxyx()
    pair = theme.PAIR_ALERT if alert else theme.PAIR_ACCENT
    win.bkgd(" ", theme.attr(pair, bold=True))
    start = max(0, (h - len(lines)) // 2)
    for i, line in enumerate(lines):
        _center(win, start + i, line, theme.attr(pair, bold=True))
    win.noutrefresh()
