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
HW_BIN = Path(os.environ.get("FOUNDATIONHUB_HW_BIN", "/usr/local/lib/foundationhub"))
ETC = Path(os.environ.get("FOUNDATIONHUB_ETC", "/etc/foundationhub"))
FRANK_SOCK = os.environ.get("FRANK_HUB_SOCK", "/run/frank/hub.sock")
# Operator-readable liveness/last-error breadcrumb frankd writes (daemon.py
# _write_health). Lets System Status show WHY Frank is down on a locked kiosk
# where the journal can't be read. No finding detail — status tag + traceback.
FRANK_HEALTH = Path(os.environ.get("FRANK_HEALTH", "/run/frank/frankd.health"))
# Ledger: timestamps ONLY (spec §6). The Hub can read this; it can NOT read
# Frank's detail store, which is frank:frank 0600 and never exposed. It lives in
# /run/frank (0755, operator-traversable) — NOT /var/lib/frank (0700 frank-only),
# where the operator's Hub couldn't reach it and the ledger always looked empty.
LEDGER_PATH = os.environ.get("FRANK_LEDGER", "/run/frank/ledger.timestamps")
# Frank's public login-lock summary: usernames + expiry timestamps only, so
# the login screen can refuse a locked-out account. No detail, same philosophy
# as the timestamp ledger (docs/USERS.md).
LOGIN_LOCKS = Path(os.environ.get("FRANK_LOGIN_LOCKS", "/run/frank/login.locks"))
# Where the Hub publishes which logical account holds the session, so Frank's
# collectors can attribute events per user (docs/USERS.md).
ACTIVE_USER_FILE = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER",
                                       "/run/foundationhub/active-user"))


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


# ── the active logical account (set by the login screen — docs/USERS.md) ─────
# The Linux user hosting the session stays `operator`; foundationhub accounts are
# logical users layered on top until real per-account sessions land
# [TODO(hardware)].

_active_account = None    # accounts.Account | None


def set_active_account(acct) -> None:
    global _active_account
    _active_account = acct
    if acct is not None:
        os.environ["FOUNDATIONHUB_USER"] = acct.username
        try:
            ACTIVE_USER_FILE.parent.mkdir(parents=True, exist_ok=True)
            ACTIVE_USER_FILE.write_text(acct.username + "\n")
        except OSError:
            pass   # off-device: /run/foundationhub may not exist; Frank just sees no user
    else:
        # Logout to the login roster: clear the logical user so Frank stops
        # attributing activity to them and continuous session-lock polls go quiet.
        os.environ.pop("FOUNDATIONHUB_USER", None)
        try:
            if ACTIVE_USER_FILE.exists():
                ACTIVE_USER_FILE.write_text("")
        except OSError:
            pass


def get_active_account():
    return _active_account


# Last note/file the operator saved with content — used to redact a matched
# infraction string from the source file when a lockout fires.
_last_content_path: Path | None = None

# Replacement for matched infraction text. Fixed "***" (not same-length
# stars) so regex word-boundary rules cannot re-fire on the redacted form
# after a lockout expires and the user re-opens/re-saves the content.
_REDACT_TOKEN = "***"


def note_content_path(path) -> None:
    """Remember the most recently saved content path (editor on save)."""
    global _last_content_path
    try:
        _last_content_path = Path(path) if path is not None else None
    except (TypeError, ValueError):
        _last_content_path = None


def last_content_path() -> Path | None:
    return _last_content_path


def redact_matched_in_text(text: str, matched: str) -> str:
    """Replace every case-insensitive occurrence of `matched` with ***."""
    if not matched or not text:
        return text
    out: list[str] = []
    lower = text.lower()
    needle = matched.lower()
    n = len(needle)
    i = 0
    while i < len(text):
        j = lower.find(needle, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(_REDACT_TOKEN)
        i = j + n
    return "".join(out)


def redact_infraction_in_file(matched: str, path: Path | None = None) -> bool:
    """Replace the matched infraction text in a content file with ***.

    Returns True if the file was modified. Best-effort: missing path, missing
    match, or IO errors are silent no-ops (the lockout still proceeds).
    """
    path = path if path is not None else _last_content_path
    if not matched or path is None:
        return False
    try:
        p = Path(path)
        if not p.is_file():
            return False
        original = p.read_text(encoding="utf-8")
    except OSError:
        return False
    redacted = redact_matched_in_text(original, matched)
    if redacted == original:
        return False
    try:
        p.write_text(redacted, encoding="utf-8")
        return True
    except OSError:
        return False


def redact_infraction_in_activity(matched: str) -> bool:
    """Scrub `matched` from the Hub activity spool so a frankd restart cannot
    re-classify the same line after a lockout expires.

    Best-effort; returns True if the spool was modified.
    """
    if not matched:
        return False
    path = Path(os.environ.get(
        "FOUNDATIONHUB_ACTIVITY_LOG",
        os.environ.get("FRANK_ACTIVITY_SPOOL", "/run/foundationhub/activity.log")))
    try:
        if not path.is_file():
            return False
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    redacted = redact_matched_in_text(original, matched)
    if redacted == original:
        return False
    try:
        path.write_text(redacted, encoding="utf-8")
        return True
    except OSError:
        return False


def read_login_locks() -> dict:
    """Frank's public login summary:
    {"machine_end": ts, "users": {name: ts}, "violations": {name: count}}.

    Usernames, timestamps, and bare violation COUNTS only — when and how many,
    never why (same disclosure philosophy as the timestamp ledger). The counts
    feed the login roster's per-account readout. Missing/corrupt file = no
    locks, no counts (off-device, or Frank not running)."""
    import json
    try:
        data = json.loads(LOGIN_LOCKS.read_text())
        return {"machine_end": float(data.get("machine_end", 0)),
                "users": {str(k): float(v)
                          for k, v in data.get("users", {}).items()},
                "violations": {str(k): int(v)
                               for k, v in data.get("violations", {}).items()}}
    except (OSError, ValueError, TypeError):
        return {"machine_end": 0.0, "users": {}, "violations": {}}


# ── System Status (read-only identity + basic health checks) ─────────────────

def get_user_identity() -> tuple[str, str]:
    """Return (username, uid) for display. Never raises."""
    if _active_account is not None:
        return _active_account.username, str(os.getuid())
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


def check_local_ai() -> bool:
    """Is the on-device model server (frank-ai / llama-server) answering?"""
    try:
        from .aiclient import AssistantClient
        return AssistantClient().reachable()
    except Exception:
        return False


# Operator-readable breadcrumb written by install/11 and frank-ai wrapper paths.
AI_STATUS_PATHS = (
    Path(os.environ.get("FOUNDATIONHUB_AI_STATUS",
                        "/var/lib/foundationhub/ai-status")),
    Path("/run/foundation-ai/status"),
)


def local_ai_health() -> str:
    """Short reason when LOCAL AI is down — for System Status on a kiosk.

    Prefer a live TCP/HTTP probe; fall back to the install-time status file
    (missing binary/libs/model) when the port is closed.
    """
    if check_local_ai():
        return ""
    for path in AI_STATUS_PATHS:
        try:
            text = path.read_text().strip()
        except OSError:
            continue
        if not text:
            continue
        # Prefer a state= line if present; else first non-comment line.
        state = ""
        detail = ""
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if ln.startswith("state="):
                state = ln.split("=", 1)[1].strip()
            elif ln.startswith("detail="):
                detail = ln.split("=", 1)[1].strip()
            elif not detail:
                detail = ln
        if state and detail:
            return f"{state}: {detail}"[:72]
        if state:
            return state[:72]
        if detail:
            return detail[:72]
    return "not listening on 127.0.0.1:8080 (runtime/model missing or service down)"


def frank_health() -> str:
    """A short reason when Frank is down, for System Status to display on a
    locked kiosk. '' means healthy/reachable; otherwise a one-line summary from
    frankd's health breadcrumb (status tag + the last traceback line), or a
    generic hint if the daemon never even wrote one (e.g. it can't start)."""
    if FrankClient().is_alive():
        return ""
    try:
        text = FRANK_HEALTH.read_text()
    except OSError:
        return "not running (no health file — daemon may not be starting)"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    status = next((ln[len("status="):].strip()
                   for ln in lines if ln.startswith("status=")), "down")
    # The real error is the last traceback line (skip our status=/ts= header).
    err = ""
    for ln in reversed(lines):
        if not ln.startswith(("status=", "ts=")):
            err = ln.strip()
            break
    return f"{status}: {err}".rstrip(": ").strip()


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
        """Non-blocking check for a pending warn/lockout. None if offline/none.

        Returns a dict with at least ``type`` and ``raw``. Common optional keys
        from frankd: delivery, user, scope, remaining, negotiable, matched, msg.
        ``matched`` is URL-decoded (frankd percent-encodes it for the wire).
        """
        resp = self._send("poll")
        if not resp:
            return None
        # Protocol is line-oriented "TYPE key=val ... msg=<free text>".
        head, _, msg = resp.partition("msg=")
        parts = head.split()
        if not parts:
            return None
        out: dict = {"type": parts[0], "raw": resp}
        if msg or "msg=" in resp:
            out["msg"] = msg.strip()
        from urllib.parse import unquote
        for tok in parts[1:]:
            key, _, val = tok.partition("=")
            if not key:
                continue
            if key == "matched" and val:
                out[key] = unquote(val)
            else:
                out[key] = val
        return out

    def negotiate(self, plea: str) -> dict | None:
        """Submit a plea against a NEGOTIABLE lockout. Frank decides and can
        refuse — this is a request, not a command (docs/FRANK-LOCAL-AI.md §4).

        Returns {"outcome", "removed", "remaining", "msg"} or None if Frank is
        unreachable. The wire protocol is line-oriented, so the plea is collapsed
        to a single line before sending.
        """
        plea = " ".join((plea or "").split())
        resp = self._send(f"negotiate {plea}")
        if not resp or not resp.startswith("negotiate"):
            return None
        out = {"outcome": "", "removed": 0, "remaining": 0, "msg": ""}
        body = resp[len("negotiate"):].strip()
        # Everything before " msg=" is space-separated key=val; msg is free text.
        head, _, msg = body.partition("msg=")
        out["msg"] = msg.strip()
        for tok in head.split():
            key, _, val = tok.partition("=")
            if key == "outcome":
                out["outcome"] = val
            elif key in ("removed", "remaining"):
                try:
                    out[key] = int(val)
                except ValueError:
                    pass
        return out
