"""Home Hub screens. `build_home(app)` assembles the top-level menu (spec §5)."""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen
from ..ui import MenuItem, KEYS_BACK

from . import programs, recreation, functions, logs, power


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
    """Top-level Home Hub (feedback #8 — reworked IA).

    Five entries: Programs (which now holds Notes + Notes Search), Recreation,
    Settings (was Functions; also holds Network + the Status readout), Logs,
    Power. The old top-level Personal File and Assistant entries were folded in
    / hidden — Notes lives under Programs, Assistant is off the menu for now.
    """
    items = [
        MenuItem(labels.PROGRAMS, lambda a: programs.screen()),
        MenuItem(labels.RECREATION, lambda a: recreation.screen()),
        MenuItem(labels.SETTINGS, lambda a: functions.screen()),
        MenuItem(labels.LOGS, lambda a: logs.screen()),
        MenuItem(labels.POWER, lambda a: power.screen()),
    ]
    return HomeScreen(labels.HUB_TITLE, items,
                      subtitle=labels.HUB_SUBTITLE, status=labels.HINT_TOP)
