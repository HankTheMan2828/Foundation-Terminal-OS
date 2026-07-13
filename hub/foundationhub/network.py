"""Network status + WiFi radio control (Settings → NETWORK).

Curses-free and testable. On target, talks to NetworkManager via `nmcli`
when present; off-device every call degrades to an honest status string
instead of crashing the Hub.

Policy note: this is *general* connectivity (Web Access, everyday use).
System-update transport policy (usb / wired / wireless opt-in) stays in
`updates.py` and is intentionally stricter.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional


RunFn = Callable[..., subprocess.CompletedProcess]


def _default_run(argv: list[str], *, timeout: float = 5) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def nmcli_available(which: Callable[[str], Optional[str]] = shutil.which) -> bool:
    return which("nmcli") is not None


# ── live status ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkStatus:
    """Snapshot for the Settings NETWORK screen header."""
    connected: bool
    state: str              # nmcli general STATE, or a short fallback
    iface: str              # default-route interface, or ""
    kind: str               # "ethernet" | "wifi" | "other" | "none"
    ssid: str               # active WiFi SSID when kind==wifi, else ""
    wifi_radio: str         # "enabled" | "disabled" | "unknown" | "n/a"
    summary: str            # one-line operator-facing status


def default_route_iface() -> str:
    """Read the default IPv4 route interface from /proc (no subprocess)."""
    try:
        with open("/proc/net/route") as fh:
            for line in fh.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 2 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        pass
    return ""


def iface_is_wireless(iface: str) -> bool:
    if not iface:
        return False
    return os.path.isdir(f"/sys/class/net/{iface}/wireless")


def classify_iface(iface: str) -> str:
    """Map an interface name to a short kind label."""
    if not iface:
        return "none"
    if iface_is_wireless(iface) or iface.startswith(("wlan", "wlp", "wl")):
        return "wifi"
    if iface.startswith(("eth", "en", "em")):
        return "ethernet"
    # USB tethering / bridges / tunnels — honest "other", not wifi.
    return "other"


def parse_nmcli_general_state(text: str) -> str:
    """`nmcli -t -f STATE general` → first field, lowercased."""
    line = (text or "").strip().splitlines()
    if not line:
        return ""
    # STATE alone is one value; sometimes "connected (site only)" etc.
    return line[0].strip().lower()


def parse_wifi_radio(text: str) -> str:
    """`nmcli radio wifi` → enabled|disabled|unknown."""
    val = (text or "").strip().splitlines()
    if not val:
        return "unknown"
    word = val[0].strip().lower()
    if word in ("enabled", "disabled"):
        return word
    return "unknown"


def parse_active_ssid(text: str) -> str:
    """`nmcli -t -f TYPE,STATE,NAME connection show --active` → first wifi SSID."""
    for line in (text or "").splitlines():
        # TYPE:STATE:NAME  (NAME may contain colons — rare; take rest after 2nd)
        parts = line.split(":")
        if len(parts) < 3:
            continue
        conn_type = parts[0].strip().lower()
        state = parts[1].strip().lower()
        name = ":".join(parts[2:]).strip()
        if conn_type in ("802-11-wireless", "wifi", "wireless") and state == "activated":
            return name
    return ""


def network_status(*, run: RunFn = _default_run,
                   which: Callable[[str], Optional[str]] = shutil.which,
                   route_iface: Optional[str] = None,
                   wireless: Optional[bool] = None) -> NetworkStatus:
    """Build a NetworkStatus. Injectables keep unit tests off the real stack."""
    iface = default_route_iface() if route_iface is None else route_iface
    kind = classify_iface(iface)
    if wireless is not None and iface:
        kind = "wifi" if wireless else (
            "ethernet" if kind != "wifi" else "ethernet")

    state = "unknown"
    connected = False
    wifi_radio = "n/a"
    ssid = ""

    if not nmcli_available(which):
        # Fallback: any global address ⇒ connected-ish.
        if iface:
            connected = True
            state = "connected (no nmcli)"
        else:
            state = "unavailable"
        summary = _summary(connected, state, iface, kind, ssid, wifi_radio)
        return NetworkStatus(connected, state, iface, kind, ssid, wifi_radio, summary)

    try:
        res = run(["nmcli", "-t", "-f", "STATE", "general"], timeout=3)
        state = parse_nmcli_general_state(res.stdout) or "unknown"
        connected = state.startswith("connected")
    except Exception:
        state = "unknown"

    try:
        res = run(["nmcli", "radio", "wifi"], timeout=3)
        wifi_radio = parse_wifi_radio(res.stdout)
    except Exception:
        wifi_radio = "unknown"

    if kind == "wifi" or connected:
        try:
            res = run(
                ["nmcli", "-t", "-f", "TYPE,STATE,NAME",
                 "connection", "show", "--active"],
                timeout=3,
            )
            ssid = parse_active_ssid(res.stdout)
            if ssid and kind == "none":
                kind = "wifi"
        except Exception:
            pass

    summary = _summary(connected, state, iface, kind, ssid, wifi_radio)
    return NetworkStatus(connected, state, iface, kind, ssid, wifi_radio, summary)


def _summary(connected: bool, state: str, iface: str, kind: str,
             ssid: str, wifi_radio: str) -> str:
    if not connected:
        base = f"OFFLINE · {state}" if state and state != "unknown" else "OFFLINE"
        if wifi_radio == "disabled":
            base += " · WiFi radio off"
        return base
    if kind == "ethernet":
        return f"ONLINE · ethernet ({iface or '?'})"
    if kind == "wifi":
        name = ssid or iface or "?"
        return f"ONLINE · WiFi · {name}"
    if iface:
        return f"ONLINE · {iface}"
    return f"ONLINE · {state}"


# ── WiFi radio ───────────────────────────────────────────────────────────────

def set_wifi_radio(on: bool, *, run: RunFn = _default_run,
                   which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """Enable or disable the WiFi radio via nmcli. Never raises."""
    if not nmcli_available(which):
        return "nmcli: not available (off-device or NetworkManager not installed)"
    arg = "on" if on else "off"
    try:
        res = run(["nmcli", "radio", "wifi", arg], timeout=10)
    except Exception as exc:
        return f"wifi radio: {exc}"
    if res.returncode != 0:
        err = (res.stderr or res.stdout).strip() or "failed"
        return f"wifi radio: {err}"
    return f"WiFi radio → {'ON' if on else 'OFF'}"


def wifi_radio_status(*, run: RunFn = _default_run,
                      which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """Short label for the menu status column."""
    if not nmcli_available(which):
        return "n/a"
    try:
        res = run(["nmcli", "radio", "wifi"], timeout=3)
        word = parse_wifi_radio(res.stdout)
    except Exception:
        return "n/a"
    if word == "enabled":
        return "ON"
    if word == "disabled":
        return "OFF"
    return "n/a"
