"""Settings / Configuration (spec §5).

Covers resource limits, network, user/auth, and theme & sound.

There is intentionally NOTHING here for the overseer. The operator has no power
over Frank, ever — no sensitivity knob, no thresholds, no enable/disable, no
config. Frank's settings are root-owned and unreachable from within the running
OS. (This overrides the spec §5 mention of exposed sensitivity tuning, at the
user's explicit direction — see docs/OPEN-QUESTIONS.md §5.)
"""
from __future__ import annotations

from .. import labels, theme
from ..app import MenuScreen, Launch
from ..ui import MenuItem


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
    return MenuScreen(labels.SET_THEME, items)


def screen():
    items = [
        MenuItem(labels.SET_RESOURCE, lambda a: Launch(["btop"]), hint="view/limit"),
        MenuItem(labels.SET_NETWORK, lambda a: Launch(["nmtui"]), hint="nmtui"),
        MenuItem(labels.SET_AUTH, lambda a: Launch(["passwd"]), hint="passwd"),
        MenuItem(labels.SET_THEME, lambda a: _theme_screen()),
    ]
    return MenuScreen(labels.SETTINGS, items)
