"""Negotiation screen — talk Frank down from a NEGOTIABLE lockout.

Frank decides; this screen only lets the user *ask* (docs/FRANK-LOCAL-AI.md
§4). It is shown only for a session-scope negotiable lock — a machine/serious
lock is never negotiable and never reaches here. The user types a statement,
Frank's rule-bounded engine answers, and the reply (a baked negotiation line)
is shown. On a "released" outcome the lock is gone and we return.

Reachable from the full-screen lockout banner when Frank reports
``negotiable=1`` (press N). The lockout banner always states whether
negotiation is available and how to open this screen.
"""
from __future__ import annotations

import curses

from .. import labels, theme
from ..app import POP, Screen
from ..session import FrankClient
from ..ui import KEYS_BACK, LineEdit


class NegotiateScreen(Screen):
    title = labels.NEGOTIATE_TITLE
    subtitle = labels.NEGOTIATE_SUBTITLE

    def __init__(self, client: FrankClient | None = None):
        self.client = client or FrankClient()
        self.edit = LineEdit(limit=200)
        self.message = labels.NEGOTIATE_INTRO
        self.editing = True
        self._released = False

    def draw(self, win, top: int, left: int) -> None:
        _, w = win.getmaxyx()
        width = max(1, w - 2 * left)
        rows = [self.message, ""]
        if self.editing:
            rows.append(f"{labels.NEGOTIATE_PROMPT}: {self.edit.display()}")
        else:
            rows.append(labels.NEGOTIATE_DONE)
        for i, line in enumerate(rows):
            try:
                win.addstr(top + i, left, line[:width], theme.attr(theme.PAIR_NORMAL))
            except curses.error:
                pass

    def status_text(self) -> str:
        return labels.NEGOTIATE_HINT

    def handle_key(self, key: int, app):
        if not self.editing:
            if key in KEYS_BACK:
                return POP
            self.editing = True
            self.edit = LineEdit(limit=200)
            return None
        result = self.edit.handle(key)
        if result == "cancel":
            return POP
        if result == "submit":
            plea = self.edit.value.strip()
            if not plea:
                return None
            resp = self.client.negotiate(plea)
            if resp is None:
                self.message = labels.NEGOTIATE_OFFLINE
            else:
                self.message = resp.get("msg") or resp.get("outcome", "")
                if resp.get("outcome") == "released":
                    self._released = True
                    return POP        # the restriction is lifted; nothing to negotiate
            self.editing = False
        return None
