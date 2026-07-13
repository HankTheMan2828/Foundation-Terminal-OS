"""Update-system backend (docs/UPDATE-SYSTEM.md) — curses-free, testable.

The Hub side of the update system: read the machine's version identity
(/etc/foundation-release) and transport policy (/etc/foundation-update.conf),
check the latest GitHub release on demand, and hand the actual work to the
ROOT helper (pkexec foundation-update) — the Hub itself never has the
privilege to change anything.

There is deliberately NO daemon and NO background check anywhere: every
function here runs only when the operator opens Settings > SYSTEM UPDATE and
asks. The checks the Hub does (tier, policy, transport) are UX pre-checks;
the root helper re-verifies all of them authoritatively.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

GITHUB_REPO = "HankTheMan2828/Foundation-Terminal-OS"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
HELPER = "/usr/local/bin/foundation-update"

POLICY_MODES = ("usb", "usb+wired", "usb+wired+wireless")
POLICY_DEFAULT = "usb+wired"
POLICY_LABELS = {
    "usb": "USB ONLY",
    "usb+wired": "USB + WIRED",
    "usb+wired+wireless": "USB + WIRED + WIRELESS",
}


def release_path() -> Path:
    return Path(os.environ.get("FOUNDATION_RELEASE_FILE",
                               "/etc/foundation-release"))


def policy_path() -> Path:
    return Path(os.environ.get("FOUNDATION_UPDATE_CONF",
                               "/etc/foundation-update.conf"))


# ── version identity ─────────────────────────────────────────────────────────
def parse_release(text: str) -> dict:
    """/etc/foundation-release → {'version', 'built', 'profile', 'history'}.
    Repeated history= lines are the append-only install/update trail."""
    info = {"version": "unversioned", "built": "", "profile": "",
            "history": []}
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key == "history":
            info["history"].append(value)
        elif key in info:
            info[key] = value
    return info


def current_release() -> dict:
    try:
        return parse_release(release_path().read_text())
    except OSError:
        return parse_release("")


def current_version() -> str:
    return current_release()["version"]


_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def version_tuple(tag: str) -> tuple | None:
    """Parse a release tag into a comparable triple.

    Current scheme: ``v0.1.0`` → ``(0, 1, 0)``.
    Legacy scheme (still readable on installed machines):
    ``TerminalOS-v0.0.24`` → ``(0, 0, 24)``.
    Returns None when unparsable.
    """
    m = _VERSION_RE.search(tag or "")
    return tuple(int(g) for g in m.groups()) if m else None


def is_newer(latest: str, current: str) -> bool:
    """True when `latest` should be offered over `current`. Comparable
    versions compare numerically; an unversioned/dev machine treats any
    parsable release as an update; otherwise only inequality of two
    unparsable strings never offers anything (no basis to prefer either)."""
    lt, ct = version_tuple(latest), version_tuple(current)
    if lt is None:
        return False
    if ct is None:
        return True
    return lt > ct


# ── transport policy ─────────────────────────────────────────────────────────
def parse_policy(text: str) -> str:
    """`transports = <mode>` → the mode. Anything unreadable or invalid
    falls back to the shipped default — garbage never widens policy."""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("transports"):
            _, _, value = line.partition("=")
            value = value.strip()
            if value in POLICY_MODES:
                return value
    return POLICY_DEFAULT


def policy() -> str:
    try:
        return parse_policy(policy_path().read_text())
    except OSError:
        return POLICY_DEFAULT


def policy_label(mode: str | None = None) -> str:
    return POLICY_LABELS.get(mode or policy(), POLICY_DEFAULT.upper())


# ── live transport check (UX pre-check; the helper re-enforces) ─────────────
def default_route_iface() -> str | None:
    try:
        with open("/proc/net/route") as fh:
            for line in fh.readlines()[1:]:
                fields = line.split()
                if len(fields) >= 2 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        pass
    return None


def iface_is_wireless(iface: str) -> bool:
    return os.path.isdir(f"/sys/class/net/{iface}/wireless")


def transport_check(mode: str | None = None, *,
                    iface: str | None = None,
                    wireless: bool | None = None) -> str | None:
    """None when a network update may proceed under `mode`, else the reason
    it may not. `iface`/`wireless` are injectable for tests."""
    mode = mode or policy()
    if mode == "usb":
        return "updates arrive by USB on this machine (policy: usb)"
    if iface is None:
        iface = default_route_iface()
    if not iface:    # None or "" — no default route
        return "no network route — connect ethernet first"
    if wireless is None:
        wireless = iface_is_wireless(iface)
    if wireless and mode != "usb+wired+wireless":
        return (f"route is wireless ({iface}) — wired only under policy "
                f"{policy_label(mode)}")
    return None


# ── the on-demand release check ──────────────────────────────────────────────
def check_latest(timeout: int = 10) -> tuple[str, str | None]:
    """(latest_tag, error). One HTTPS GET, only ever called on demand."""
    req = urllib.request.Request(
        API_LATEST, headers={"User-Agent": "foundationhub",
                             "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        return "", f"check failed: {exc}"
    tag = data.get("tag_name", "")
    if not tag:
        return "", "check failed: release has no tag"
    return tag, None


# ── root-helper invocations (pkexec; the helper revalidates everything) ─────
def _run_helper(args: list[str], stdin: str) -> str | None:
    """Returns an error string or None. Import-local subprocess keeps the
    module import-light for tests."""
    import shutil
    import subprocess
    if shutil.which("pkexec") is None or not os.path.exists(HELPER):
        return "update helper not installed on this machine"
    try:
        res = subprocess.run(["pkexec", HELPER, *args], input=stdin,
                             text=True, capture_output=True, timeout=1800)
    except Exception as exc:
        return f"update failed: {exc}"
    if res.returncode != 0:
        return (res.stderr or res.stdout).strip() or "update failed"
    return None


def apply_update(setup_code: str) -> str | None:
    return _run_helper(["apply"], f"{setup_code}\n")


def set_policy(mode: str, setup_code: str) -> str | None:
    if mode not in POLICY_MODES:
        return f"unknown policy {mode!r}"
    return _run_helper(["set-policy", mode], f"{setup_code}\n")
