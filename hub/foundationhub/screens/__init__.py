"""Home Hub screens. `build_home(app)` assembles the top-level menu (spec §5)."""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen
from ..ui import MenuItem, KEYS_BACK

from . import programs, recreation, functions, status, logs, notes, aichat, power


class HomeScreen(MenuScreen):
    """Top-level hub. Esc/Backspace do NOT log out here (there's nowhere back
    to go — the Hub is the login shell). `q` opens Power (matches HINT_TOP)."""

    def handle_key(self, key, app):
        if key in (ord("q"), ord("Q")):
            return power.screen()
        if key in KEYS_BACK:
            return None  # swallow: no accidental logout from the root
        return self.menu.handle_key(key, app)


def build_home(app):
    """Top-level Home Hub. Order matches labels.py / the spec §5 listing."""
    items = [
        MenuItem(labels.PROGRAMS, lambda a: programs.screen()),
        MenuItem(labels.RECREATION, lambda a: recreation.screen()),
        MenuItem(labels.FUNCTIONS, lambda a: functions.screen()),
        MenuItem(labels.STATUS, lambda a: status.screen()),
        MenuItem(labels.LOGS, lambda a: logs.screen()),
        MenuItem(labels.NOTES, lambda a: notes.screen()),
        MenuItem(labels.ASSISTANT, lambda a: aichat.screen()),
        MenuItem(labels.POWER, lambda a: power.screen()),
    ]
    return HomeScreen(labels.HUB_TITLE, items,
                      subtitle=labels.HUB_SUBTITLE, status=labels.HINT_TOP)
