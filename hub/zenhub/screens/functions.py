"""Functions Control — REAL system toggles only, no cosmetic elements (spec §5).

Every action here shells out to an actual hardware helper (see hardware/,
install/04, install/05). Off-device, calls return a clear status string.
"""
from __future__ import annotations

from .. import labels, session, theme
from ..app import MenuScreen, Launch
from ..ui import MenuItem


def _set_status(msg: str):
    """Wrap a result string into an app action that shows it in the status bar."""
    def action(app):
        app.status_message = msg() if callable(msg) else msg
    return action


def _brightness_screen():
    items = [
        MenuItem(f"{p}%", _set_status(lambda p=p: session.set_brightness(p)), hint="synced")
        for p in (25, 50, 75, 100)
    ]
    return MenuScreen(f"{labels.FN_BRIGHTNESS}", items,
                      subtitle="dual-panel synced (spec §7)")


def _power_screen():
    items = [
        MenuItem(p.upper(), _set_status(lambda p=p: session.set_power_profile(p)))
        for p in ("power-saver", "balanced", "performance")
    ]
    return MenuScreen(labels.FN_POWER_PROFILE, items)


def _theme_screen():
    def _pal(name):
        def action(app):
            theme.set_palette(name)
            theme.init(app.stdscr)
            app.status_message = f"palette → {name} (restart Hub to fully apply)"
        return action
    items = [
        MenuItem("AMBER PHOSPHOR", _pal(theme.PALETTE_AMBER)),
        MenuItem("GREEN PHOSPHOR", _pal(theme.PALETTE_GREEN)),
        MenuItem("SOUND (mixer)", lambda a: Launch(["alsamixer"]), hint="alsamixer"),
    ]
    return MenuScreen(labels.FN_THEME, items)


def screen():
    items = [
        MenuItem(labels.FN_BRIGHTNESS, lambda a: _brightness_screen()),
        MenuItem(f"{labels.FN_SECOND_SCREEN} · ON",
                 _set_status(lambda: session.toggle_second_screen(True))),
        MenuItem(f"{labels.FN_SECOND_SCREEN} · OFF",
                 _set_status(lambda: session.toggle_second_screen(False))),
        MenuItem(labels.FN_POWER_PROFILE, lambda a: _power_screen()),
        MenuItem(labels.FN_THEME, lambda a: _theme_screen()),
    ]
    return MenuScreen(labels.FUNCTIONS, items)
