"""Logs — two distinct sections (spec §5).

  1. System records — raw journald/kernel/auth, launched read-only.
  2. Overseer ledger — Frank's visible ledger: TIMESTAMPS ONLY (spec §6).
     No categories, severity, descriptions, or content. Detail is frank-only
     and is never surfaced here or anywhere in the Hub.
"""
from __future__ import annotations

import curses

from .. import labels, session
from ..app import MenuScreen, Screen, Launch, POP
from ..ui import MenuItem, draw_chrome, draw_statusbar, KEYS_UP, KEYS_DOWN, KEYS_BACK
from .. import theme


class LedgerScreen(Screen):
    """Scrollable view of the timestamp-only overseer ledger (spec §6)."""

    title = labels.LOG_OVERSEER
    subtitle = "timestamps only — by design (§6)"

    def __init__(self):
        self.lines = session.read_overseer_ledger()
        self.offset = 0

    def draw(self, win, top, left):
        h, w = win.getmaxyx()
        page = h - top - 2
        if not self.lines:
            win.addstr(top, left, "(ledger empty — resets daily, §6)",
                       theme.attr(theme.PAIR_DIM, dim=True))
            return
        view = self.lines[self.offset:self.offset + page]
        for i, line in enumerate(view):
            win.addstr(top + i, left, line[: w - left - 2],
                       theme.attr(theme.PAIR_NORMAL))

    def status_text(self):
        return f"{labels.HINT_NAV}   ({len(self.lines)} entries)"

    def handle_key(self, key, app):
        if key in KEYS_UP:
            self.offset = max(0, self.offset - 1)
        elif key in KEYS_DOWN:
            self.offset += 1
        elif key in KEYS_BACK:
            return POP
        return None


def screen():
    items = [
        MenuItem(labels.LOG_SYSTEM,
                 lambda a: Launch(["journalctl", "-e", "--no-pager"]),
                 hint="journald/kernel/auth"),
        MenuItem(labels.LOG_OVERSEER, lambda a: LedgerScreen(),
                 hint="timestamps only"),
    ]
    return MenuScreen(labels.LOGS, items)
