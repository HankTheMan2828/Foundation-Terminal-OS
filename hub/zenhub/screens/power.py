"""Power — log out / reboot / shut down.

Log out exits the Hub, which (since the Hub is the login shell, spec §4) ends
the session. Reboot/shutdown shell out to systemctl.
"""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen, Launch, QUIT
from ..ui import MenuItem


def screen():
    items = [
        MenuItem(labels.POWER_LOGOUT, lambda a: QUIT),
        MenuItem(labels.POWER_REBOOT, lambda a: Launch(["systemctl", "reboot"])),
        MenuItem(labels.POWER_SHUTDOWN, lambda a: Launch(["systemctl", "poweroff"])),
    ]
    return MenuScreen(labels.POWER, items,
                      subtitle="log out ends the session (§4)")
