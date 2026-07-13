"""Settings → NETWORK — connectivity status, WiFi radio, and nmtui.

Ethernet: plug in a cable and NetworkManager brings the link up — no extra
step. WiFi: turn the radio on here, then CONFIGURE NETWORK (nmtui) to pick
an SSID and enter a password.

This is general internet access (Web Access, everyday use). System-update
wireless policy remains under Settings → SYSTEM UPDATE and is separate.
"""
from __future__ import annotations

import curses

from .. import labels, network, theme
from ..app import POP, Launch, Screen
from ..ui import KEYS_BACK, Menu, MenuItem


class NetworkScreen(Screen):
    title = labels.STATUS_NETWORK
    subtitle = labels.NET_SUBTITLE

    def __init__(self):
        self.message = ""
        self._snap = network.network_status()
        self.menu = Menu(self._build())

    def _build(self) -> list[MenuItem]:
        radio = self._snap.wifi_radio
        return [
            MenuItem(labels.NET_WIFI_ON,
                     lambda a: self._wifi(True),
                     hint="nmcli radio wifi on",
                     status=lambda: "◄" if radio == "enabled" else ""),
            MenuItem(labels.NET_WIFI_OFF,
                     lambda a: self._wifi(False),
                     hint="nmcli radio wifi off",
                     status=lambda: "◄" if radio == "disabled" else ""),
            MenuItem(labels.NET_CONFIGURE,
                     lambda a: Launch(["nmtui"],
                                      missing_hint=labels.NET_NMTUI_MISSING),
                     hint="join WiFi / edit connections"),
            MenuItem(labels.NET_REFRESH,
                     lambda a: self._refresh(),
                     hint="re-read link state"),
        ]

    def _wifi(self, on: bool):
        self.message = network.set_wifi_radio(on)
        self._refresh()
        return None

    def _refresh(self):
        self._snap = network.network_status()
        index = self.menu.index
        self.menu = Menu(self._build())
        self.menu.set_index(index)
        return None

    def draw(self, win, top: int, left: int) -> None:
        row = top
        try:
            h, w = win.getmaxyx()
            width = max(8, w - left - 2)

            win.addstr(row, left, labels.NET_STATUS_HEADING,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
            summary = self._snap.summary[:width]
            pair = theme.PAIR_NORMAL if self._snap.connected else theme.PAIR_WARN
            win.addstr(row, left, summary,
                       theme.attr(pair, bold=not self._snap.connected))
            row += 1

            detail_bits = []
            if self._snap.iface:
                detail_bits.append(f"iface {self._snap.iface}")
            if self._snap.kind and self._snap.kind not in ("none",):
                detail_bits.append(self._snap.kind)
            radio = self._snap.wifi_radio
            if radio not in ("n/a", ""):
                detail_bits.append(f"wifi radio {radio}")
            if detail_bits:
                win.addstr(row, left, " · ".join(detail_bits)[:width],
                           theme.attr(theme.PAIR_DIM, dim=True))
                row += 1

            row += 1
            win.addstr(row, left, labels.NET_ETHERNET_HINT[:width],
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 2

            self.menu.draw(win, row, left)

            if self.message:
                prompt_row = h - 4
                win.addstr(prompt_row, left, self.message[:width].upper(),
                           theme.attr(theme.PAIR_WARN, bold=True))
        except curses.error:
            pass

    def status_text(self) -> str:
        return labels.HINT_NAV

    def handle_key(self, key, app):
        # Clear transient message on navigation so it doesn't stick forever.
        if key in KEYS_BACK:
            return POP
        result = self.menu.handle_key(key, app)
        if result is not None:
            return result
        return None


def screen():
    return NetworkScreen()
