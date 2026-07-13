"""Web Access — pick a browser and open DuckDuckGo.

Curses-free launch planner used by Programs → WEB ACCESS.

Preference order (operator direction, post-v0.1.0):
  1. Graphical browser when a display session is available (Firefox, Chromium…).
     Homepage is DuckDuckGo.
  2. Text browser fallback (w3m / lynx / links) on the console — always the
     reliable path on the kernel-VT kiosk and under kitty.
  3. Clear offline / not-installed messages when neither path works.

General connectivity (any online link — ethernet or WiFi) is enough; this is
*not* gated by the system-update wireless policy.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from . import network as netmod
from . import session

# DuckDuckGo — graphical home + text-friendly HTML endpoint.
DDG_HOME = "https://duckduckgo.com"
DDG_HTML = "https://html.duckduckgo.com/html/"

# Graphical candidates: (binary, argv-with-{url} placeholder via list builder).
# Arch package names are the common ones; profiles may install more.
_GUI_BROWSERS: Sequence[tuple[str, tuple[str, ...]]] = (
    # firefox URL  (also opens from a cold start)
    ("firefox", ("firefox", "--new-window")),
    ("firefox-esr", ("firefox-esr", "--new-window")),
    ("chromium", ("chromium", "--new-window")),
    ("chromium-browser", ("chromium-browser", "--new-window")),
    ("google-chrome-stable", ("google-chrome-stable", "--new-window")),
    ("google-chrome", ("google-chrome", "--new-window")),
    ("brave", ("brave", "--new-window")),
    ("brave-browser", ("brave-browser", "--new-window")),
    # DuckDuckGo desktop browser if ever packaged under these names
    ("duckduckgo", ("duckduckgo",)),
    ("ddg", ("ddg",)),
)

_TEXT_BROWSERS: Sequence[tuple[str, tuple[str, ...]]] = (
    # w3m is the preferred text path (shipped in install/packages.txt).
    ("w3m", ("w3m", "-v")),
    ("lynx", ("lynx",)),
    ("links", ("links",)),
    ("elinks", ("elinks",)),
)


@dataclass(frozen=True)
class LaunchPlan:
    """Either a ready argv, or an error string for the status bar."""
    argv: list[str] | None
    error: str | None
    mode: str               # "gui" | "text" | "none"
    missing_hint: str = "[ not installed — see install/packages.txt ]"

    @property
    def ok(self) -> bool:
        return bool(self.argv) and not self.error


def display_available(env: Optional[dict] = None) -> bool:
    """True when a graphical session looks reachable (X11 or Wayland)."""
    e = env if env is not None else os.environ
    if e.get("WAYLAND_DISPLAY") or e.get("DISPLAY"):
        return True
    # Last-ditch: X11 socket dir present (rare on pure VT, common under X).
    return os.path.isdir("/tmp/.X11-unix")


def which_first(names: Sequence[str],
                which: Callable[[str], Optional[str]] = shutil.which) -> Optional[str]:
    for name in names:
        if which(name):
            return name
    return None


def plan_launch(*,
                online: Optional[bool] = None,
                gui: Optional[bool] = None,
                which: Callable[[str], Optional[str]] = shutil.which,
                env: Optional[dict] = None) -> LaunchPlan:
    """Decide how to open Web Access. All IO is injectable for tests."""
    if online is None:
        online = session.check_network()
    if not online:
        return LaunchPlan(
            None,
            "NO NETWORK — connect ethernet or enable WiFi in SETTINGS → NETWORK",
            "none",
        )

    use_gui = display_available(env) if gui is None else gui
    if use_gui:
        for binary, prefix in _GUI_BROWSERS:
            if which(binary):
                argv = list(prefix) + [DDG_HOME]
                return LaunchPlan(argv, None, "gui")

    for binary, prefix in _TEXT_BROWSERS:
        if which(binary):
            argv = list(prefix) + [DDG_HTML]
            return LaunchPlan(argv, None, "text")

    if use_gui:
        # Display exists but no browser binary at all.
        return LaunchPlan(
            None,
            "NO BROWSER — install firefox (graphical) or w3m (text)",
            "none",
        )
    return LaunchPlan(
        None,
        "NO TEXT BROWSER — install w3m (or use a graphical profile + firefox)",
        "none",
    )


def status_hint(*,
                online: Optional[bool] = None,
                gui: Optional[bool] = None,
                which: Callable[[str], Optional[str]] = shutil.which,
                env: Optional[dict] = None) -> str:
    """Short right-hand hint for the Programs menu row."""
    if online is None:
        # Cheap: prefer last-known NetworkManager state without full scan.
        try:
            online = session.check_network()
        except Exception:
            online = False
    if not online:
        return "offline"
    plan = plan_launch(online=True, gui=gui, which=which, env=env)
    if plan.mode == "gui":
        return "DuckDuckGo · gui"
    if plan.mode == "text":
        return "DuckDuckGo · text"
    return "no browser"


def connectivity_summary() -> str:
    """One-line network status for a pre-launch screen / message."""
    return netmod.network_status().summary
