"""Reusable curses widgets: CRT chrome, the highlight-and-Enter Menu, banners.

Kept deliberately small and dependency-free. Screens compose these; they don't
draw raw curses primitives themselves.
"""
from __future__ import annotations

import curses
from typing import Callable, Optional

from . import theme

# Vim + arrow navigation (spec §4).
KEYS_UP = {curses.KEY_UP, ord("k")}
KEYS_DOWN = {curses.KEY_DOWN, ord("j")}
KEYS_SELECT = {curses.KEY_ENTER, ord("\n"), ord("\r"), ord(" ")}
KEYS_BACK = {27, curses.KEY_BACKSPACE, 127, 8, ord("h")}  # Esc / Backspace / h


def draw_chrome(win, title: str, subtitle: str = "", *, scanlines: bool = True) -> tuple[int, int]:
    """Draw the CRT bezel + title bar. Returns the (top, left) of the content box."""
    # Re-assert the normal phosphor rendition as the window background BEFORE
    # erasing. A window's background attribute is sticky: it survives erase()
    # and is OR'd into every cell drawn afterwards. If anything ever leaves a
    # bold/alert background on this shared stdscr (e.g. full_screen_banner's
    # bkgd), every later screen would keep rendering bold — the palette gets
    # stuck on a saturated "super amber" and never recovers (feedback #10).
    # Resetting here, on the one path every screen redraws through, makes the
    # Hub self-healing against background-rendition leaks.
    win.bkgd(" ", theme.attr(theme.PAIR_NORMAL))
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

    # Title bar. The banner text is light amber (the frame stays base yellow) so
    # the header reads as its own band instead of the old bold-yellow that hit
    # the VT's bright slot and looked like a brighter, clashing yellow.
    _center(win, 1, title, theme.attr(theme.PAIR_AMBER, bold=True))
    if subtitle:
        _center(win, 2, subtitle, theme.attr(theme.PAIR_AMBER))
    try:
        win.hline(3, 1, curses.ACS_HLINE, w - 2)
    except curses.error:
        pass
    return (5, 4)


def draw_statusbar(win, text: str, *, warn: bool = False) -> None:
    """Bottom status line. Frank's normal warnings surface here (spec §6)."""
    h, w = win.getmaxyx()
    # Navigation hints ride the bottom line in light amber (matching the banner);
    # Frank's warnings still override to red so they never blend in.
    pair = theme.PAIR_WARN if warn else theme.PAIR_AMBER
    try:
        win.addstr(h - 2, 2, text[: w - 4].ljust(w - 4),
                   theme.attr(pair, bold=warn))
    except curses.error:
        pass


def _center(win, y: int, text: str, attr: int) -> None:
    h, w = win.getmaxyx()
    x = max(1, (w - len(text)) // 2)
    try:
        win.addstr(y, x, text[: w - 2], attr)
    except curses.error:
        pass


class LineEdit:
    """Minimal single-line editor for curses prompts. ASCII, bounded.
    Shared by the login prompts and the notes suite's name/search prompts."""

    def __init__(self, *, mask: bool = False, limit: int = 32, value: str = ""):
        self.value = value
        self.mask = mask
        self.limit = limit

    def handle(self, key: int) -> Optional[str]:
        """Returns "submit", "cancel", or None (keep editing)."""
        if key in KEYS_SELECT and key != ord(" "):
            return "submit"
        if key == 27:                      # Esc — cancel, never navigate-back
            return "cancel"
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.value = self.value[:-1]
        elif 32 <= key <= 126 and len(self.value) < self.limit:
            self.value += chr(key)
        return None

    def display(self) -> str:
        shown = "•" * len(self.value) if self.mask else self.value
        return shown + "_"


class MenuItem:
    """One selectable row. `action` gets the App; return value drives navigation."""

    def __init__(self, label: str, action: Optional[Callable] = None,
                 *, hint: str = "", enabled: bool = True,
                 status: Optional[Callable[[], str]] = None):
        self.label = label
        self.action = action
        self.hint = hint
        self.enabled = enabled
        # Optional live status, e.g. current brightness — right-aligned in the
        # row, re-evaluated on every draw so it never goes stale.
        self.status = status


class Menu:
    """Highlight + Enter list. Arrow or vim keys move; Enter fires `action`."""

    def __init__(self, items: list[MenuItem]):
        self.items = items
        self.index = 0
        self._top = 0    # scroll offset: keeps the selection on-screen
        if items and not items[0].enabled:
            for i, item in enumerate(items):
                if item.enabled:
                    self.index = i
                    break

    def move(self, delta: int) -> None:
        n = len(self.items)
        if not n:
            return
        for _ in range(n):
            self.index = (self.index + delta) % n
            if self.items[self.index].enabled:
                return

    def set_index(self, index: int) -> None:
        """Restore a selection after a rebuild: clamp to range, then settle on
        an enabled row — headers/gaps are disabled rows the selection must
        never rest on (Enter would silently do nothing there)."""
        n = len(self.items)
        if not n:
            self.index = 0
            return
        self.index = max(0, min(index, n - 1))
        if not self.items[self.index].enabled:
            self.move(+1)

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
        # Mirror the left margin on the right so the highlight bar is
        # symmetric inside the border (content starts at `left`, so the
        # left margin is `left - 1` blank columns after the border).
        width = max(0, w - 2 * left)
        # Scroll so the selected row is always visible (long note lists).
        page = max(1, h - 2 - top)
        if self.index < self._top:
            self._top = self.index
        elif self.index >= self._top + page:
            self._top = self.index - page + 1
        visible = self.items[self._top: self._top + page]
        for row, item in enumerate(visible, start=self._top):
            y = top + row - self._top
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
                text = text.ljust(28) + item.hint
            status = item.status() if item.status else ""
            if status:
                gap = max(1, width - len(text) - len(status))
                line = text + (" " * gap) + status
            else:
                line = text
            try:
                win.addstr(y, left, line[:width].ljust(width), a)
            except curses.error:
                pass


def full_screen_banner(win, lines: list[str], *, alert: bool = True) -> None:
    """Serious-severity interrupting banner (spec §6). Fills the screen."""
    win.erase()
    h, w = win.getmaxyx()
    pair = theme.PAIR_ALERT if alert else theme.PAIR_ACCENT
    a = theme.attr(pair, bold=True)
    # Paint the alert background by filling rows explicitly rather than via
    # win.bkgd(): a window background attribute is sticky and survives erase(),
    # so setting a bold background here would bleed the bold rendition into
    # every subsequent screen drawn on this shared window and lock the palette
    # to a saturated "super amber" (feedback #10). draw_chrome resets the
    # background each frame, but keeping the leak out of the source is cleaner.
    for y in range(h):
        try:
            win.addstr(y, 0, " " * (w - 1), a)
        except curses.error:
            pass
    start = max(0, (h - len(lines)) // 2)
    for i, line in enumerate(lines):
        _center(win, start + i, line, a)
    win.noutrefresh()
