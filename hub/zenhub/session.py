"""Session-side glue: hardware actions, the Frank IPC client, config paths.

Everything here is written to *degrade gracefully off-device*: if a hardware
helper or Frank's socket isn't present (e.g. running the skeleton on a laptop
that isn't the target), calls return a human-readable status string instead of
crashing the Hub.
"""
from __future__ import annotations

import getpass
import os
import shutil
import socket
import subprocess
from pathlib import Path

# Where installed hardware helpers live on the target (see install/04, hardware/).
HW_BIN = Path(os.environ.get("ZENHUB_HW_BIN", "/usr/local/lib/zenhub"))
ETC = Path(os.environ.get("ZENHUB_ETC", "/etc/zenhub"))
FRANK_SOCK = os.environ.get("FRANK_HUB_SOCK", "/run/frank/hub.sock")
# Ledger: timestamps ONLY (spec §6). The Hub can read this; it can NOT read
# Frank's detail store, which is frank:frank 0600 and never exposed.
LEDGER_PATH = os.environ.get("FRANK_LEDGER", "/var/lib/frank/ledger.timestamps")


def _run(argv: list[str], ok: str) -> str:
    """Run a helper; return an operator-facing status string, never raise."""
    exe = argv[0]
    path = HW_BIN / exe
    if path.exists():
        argv = [str(path), *argv[1:]]
    elif shutil.which(exe) is None:
        return f"{exe}: not available (off-device or not installed)"
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except Exception as exc:
        return f"{exe}: {exc}"
    if res.returncode != 0:
        return f"{exe}: {(res.stderr or res.stdout).strip() or 'failed'}"
    return ok


def _run_get(argv: list[str], fallback: str) -> str:
    """Run a read-only 'get' helper; return its first output line, never raise."""
    exe = argv[0]
    path = HW_BIN / exe
    if path.exists():
        argv = [str(path), *argv[1:]]
    elif shutil.which(exe) is None:
        return fallback
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=5)
    except Exception:
        return fallback
    if res.returncode != 0:
        return fallback
    out = res.stdout.strip()
    return out.splitlines()[0] if out else fallback


# ── Functions Control actions (spec §5 — real toggles only) ──────────────────

def set_brightness(percent: int) -> str:
    """Synced dual-panel brightness via the scoped backlight helper (spec §7)."""
    return _run(["backlight-sync", "set", str(percent)], f"brightness → {percent}%")


def toggle_second_screen(on: bool) -> str:
    """eDP-2 on/off via wlr-randr (spec §2, replaces gnome-monitor-config)."""
    return _run(["duo-screen-toggle", "on" if on else "off"],
                f"second panel {'ON' if on else 'OFF'}")


def set_power_profile(profile: str) -> str:
    return _run(["powerprofilesctl", "set", profile], f"power profile → {profile}")


def get_brightness_status() -> str:
    """Current synced backlight level, for the FUNCTIONS live-status column."""
    return _run_get(["backlight-sync", "get"], "n/a")


def get_second_screen_status() -> str:
    """Current eDP-2 (bottom panel) on/off state."""
    return _run_get(["duo-screen-toggle", "status"], "n/a")


def get_power_profile_status() -> str:
    """Current power-profiles-daemon profile."""
    return _run_get(["powerprofilesctl", "get"], "n/a")


# ── System Status (read-only identity + basic health checks) ─────────────────

def get_user_identity() -> tuple[str, str]:
    """Return (username, uid) for display. Never raises."""
    try:
        name = getpass.getuser()
    except Exception:
        name = os.environ.get("USER", "unknown")
    return name, str(os.getuid())


def check_network() -> bool:
    """Best-effort: is there an active, connected network link."""
    if shutil.which("nmcli"):
        try:
            res = subprocess.run(["nmcli", "-t", "-f", "STATE", "general"],
                                  capture_output=True, text=True, timeout=3)
            return res.returncode == 0 and res.stdout.strip().lower() == "connected"
        except Exception:
            pass
    try:
        res = subprocess.run(["ip", "-o", "addr", "show", "scope", "global"],
                              capture_output=True, text=True, timeout=3)
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


def check_audio() -> bool:
    """Best-effort: is a sound card present and visible to ALSA."""
    try:
        return bool(Path("/proc/asound/cards").read_text().strip())
    except OSError:
        return False


def check_frank() -> bool:
    """Is frankd reachable over its IPC socket (spec §6)."""
    return FrankClient().is_alive()


# ── Overseer ledger (visible: timestamps only — spec §6) ─────────────────────

def read_overseer_ledger(limit: int = 200) -> list[str]:
    """Return the visible timestamp ledger. Timestamps ONLY, by design (§6)."""
    try:
        lines = Path(LEDGER_PATH).read_text().splitlines()
    except OSError:
        return []
    return lines[-limit:]


# ── Frank IPC client (Hub <-> Frank, spec-limited surface) ───────────────────

class FrankClient:
    """READ-ONLY client. The Hub can only *receive* what Frank tells it to show.

    The operator has NO power over Frank (per explicit requirement): there is no
    method here — and no command on the wire — to tune, disable, or influence
    Frank in any way. The Hub polls for a warning/status line to DISPLAY, and
    that is the entire surface. Lockouts are enforced by a root service the Hub
    cannot reach; the Hub only reflects them.
    """

    def __init__(self, path: str = FRANK_SOCK):
        self.path = path

    def is_alive(self) -> bool:
        """Connectivity-only check: is frankd listening at all."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(self.path)
            return True
        except OSError:
            return False

    def _send(self, line: str) -> str | None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(self.path)
                s.sendall((line + "\n").encode())
                return s.recv(4096).decode().strip()
        except OSError:
            return None  # Frank not reachable (off-device / not running)

    def poll(self) -> dict | None:
        """Non-blocking check for a pending warn/lockout. None if offline/none."""
        resp = self._send("poll")
        if not resp:
            return None
        # Protocol is line-oriented "TYPE key=val ...". Kept trivial on purpose.
        parts = resp.split()
        if not parts:
            return None
        return {"type": parts[0], "raw": resp}
