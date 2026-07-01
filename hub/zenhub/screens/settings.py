"""Settings / Configuration (spec §5).

Covers resource limits, network, user/auth, theme & sound, and the ONE Frank
knob: detection sensitivity. Everything else about Frank — rules, logs,
functions — is intentionally absent and unreachable from here (spec §5, §6).
"""
from __future__ import annotations

from .. import labels, theme
from ..app import MenuScreen, Launch
from ..session import FrankClient
from ..ui import MenuItem


def _overseer_sensitivity_screen():
    """The single user-tunable Frank threshold (spec §5). 1=lenient … 5=strict.

    The Hub does NOT edit Frank's files; it asks frankd via the narrow IPC,
    which validates and applies. See docs/OPEN-QUESTIONS.md §5.
    """
    client = FrankClient()

    def _apply(level: int):
        def action(app):
            app.status_message = client.set_sensitivity(level)
        return action

    descriptions = {
        1: "1 · LENIENT — only serious flags act",
        2: "2",
        3: "3 · BALANCED (default)",
        4: "4",
        5: "5 · STRICT — elevated acts like serious",
    }
    items = [MenuItem(descriptions[n], _apply(n)) for n in range(1, 6)]
    return MenuScreen(labels.SET_OVERSEER, items,
                      subtitle="thresholds only — rules & logs are locked (§6)")


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
        MenuItem(labels.SET_OVERSEER, lambda a: _overseer_sensitivity_screen()),
    ]
    return MenuScreen(labels.SETTINGS, items)
