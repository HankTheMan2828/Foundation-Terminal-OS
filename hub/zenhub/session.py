"""Session-side glue: hardware actions, the Frank IPC client, config paths.

Everything here is written to *degrade gracefully off-device*: if a hardware
helper or Frank's socket isn't present (e.g. running the skeleton on a laptop
that isn't the target), calls return a human-readable status string instead of
crashing the Hub.
"""
from __future__ import annotations

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
