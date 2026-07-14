"""Logs — three sections (spec §5).

  1. System records — raw journald/kernel/auth, launched read-only.
  2. Overseer ledger — Frank's visible ledger: TIMESTAMPS ONLY (spec §6).
     No categories, severity, descriptions, or content. Detail is frank-only
     and is never surfaced here or anywhere in the Hub.
  3. Web Access log — foundationhub-web's persistent diagnostics, so a
     failed/odd browser session is debuggable from the kiosk itself (the
     operator has no shell to go read the file with).
"""
from __future__ import annotations

from .. import labels, session, webaccess
from ..app import MenuScreen, Screen, Launch, POP
from ..ui import MenuItem, KEYS_UP, KEYS_DOWN, KEYS_BACK
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


class WebLogScreen(Screen):
    """Scrollable view of foundationhub-web's persistent diagnostic log."""

    title = labels.LOG_WEB
    subtitle = "why the browser did (not) start — newest at the bottom"

    def __init__(self):
        self.lines = webaccess.read_web_log()
        # Land on the tail: the newest attempt is what the operator is here for.
        self.offset = max(0, len(self.lines) - 1)

    def draw(self, win, top, left):
        h, w = win.getmaxyx()
        page = max(1, h - top - 2)
        if not self.lines:
            win.addstr(top, left,
                       "(no log yet — open Programs → WEB ACCESS first)",
                       theme.attr(theme.PAIR_DIM, dim=True))
            return
        self.offset = max(0, min(self.offset, len(self.lines) - page))
        view = self.lines[self.offset:self.offset + page]
        for i, line in enumerate(view):
            warn = "ERROR" in line or "WARN" in line or "fallback" in line
            win.addstr(top + i, left, line[: w - left - 2],
                       theme.attr(theme.PAIR_WARN if warn else theme.PAIR_NORMAL))

    def status_text(self):
        return f"{labels.HINT_NAV}   ({len(self.lines)} lines)"

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
        MenuItem(labels.LOG_WEB, lambda a: WebLogScreen(),
                 hint="browser diagnostics"),
    ]
    return MenuScreen(labels.LOGS, items)
