"""Web Access — open DuckDuckGo in a console-safe browser.

Curses-free launch planner used by Programs → WEB ACCESS.

Why text-first (operator report after v0.1.1):
  The zenbook (and any cage-based) stack is a *single-app* Wayland kiosk
  (cage → kitty → Hub). Spawning Firefox/Chromium as a second Wayland client
  leaves a graphical surface that does not receive keyboard focus and cannot
  be exited cleanly — the operator is stuck. The reliable path is a text
  browser *inside the same terminal* the Hub already owns: Launch suspends
  curses, runs w3m, and resumes when the user quits (q).

Preference order:
  1. Text browser (w3m / lynx / links / elinks) → DuckDuckGo HTML.
  2. Graphical browser only when explicitly opted in via
     FOUNDATIONHUB_WEB_GUI=1 *and* a display is available (experimental;
     not used on the default kiosk).
  3. Clear offline / not-installed messages otherwise.

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

# DuckDuckGo — full site for experimental GUI; HTML endpoint for text browsers.
DDG_HOME = "https://duckduckgo.com"
DDG_HTML = "https://html.duckduckgo.com/html/"

# Opt-in only. Default kiosk must never auto-pick GUI (cage is single-client).
_GUI_OPT_IN_ENV = "FOUNDATIONHUB_WEB_GUI"

# Graphical candidates (only when opt-in + display). Kept for future multi-app
# display stacks; not the supported Web Access path today.
_GUI_BROWSERS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("firefox", ("firefox", "--new-window")),
    ("firefox-esr", ("firefox-esr", "--new-window")),
    ("chromium", ("chromium", "--new-window")),
    ("chromium-browser", ("chromium-browser", "--new-window")),
    ("google-chrome-stable", ("google-chrome-stable", "--new-window")),
    ("google-chrome", ("google-chrome", "--new-window")),
    ("brave", ("brave", "--new-window")),
    ("brave-browser", ("brave-browser", "--new-window")),
    ("duckduckgo", ("duckduckgo",)),
    ("ddg", ("ddg",)),
)

# Text browsers: argv prefix only — URL is appended. Never pass w3m -v:
# that flag is --version and exits immediately.
_TEXT_BROWSERS: Sequence[tuple[str, tuple[str, ...]]] = (
    ("w3m", ("w3m",)),
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
    return os.path.isdir("/tmp/.X11-unix")


def gui_opted_in(env: Optional[dict] = None) -> bool:
    """Graphical Web Access is experimental and off unless explicitly enabled."""
    e = env if env is not None else os.environ
    val = (e.get(_GUI_OPT_IN_ENV) or "").strip().lower()
    return val in ("1", "true", "yes", "on")


def which_first(names: Sequence[str],
                which: Callable[[str], Optional[str]] = shutil.which) -> Optional[str]:
    for name in names:
        if which(name):
            return name
    return None


def _pick_text(which: Callable[[str], Optional[str]]) -> Optional[list[str]]:
    for binary, prefix in _TEXT_BROWSERS:
        if which(binary):
            return list(prefix) + [DDG_HTML]
    return None


def _pick_gui(which: Callable[[str], Optional[str]]) -> Optional[list[str]]:
    for binary, prefix in _GUI_BROWSERS:
        if which(binary):
            return list(prefix) + [DDG_HOME]
    return None


def plan_launch(*,
                online: Optional[bool] = None,
                gui: Optional[bool] = None,
                which: Callable[[str], Optional[str]] = shutil.which,
                env: Optional[dict] = None) -> LaunchPlan:
    """Decide how to open Web Access. All IO is injectable for tests.

    `gui` when set forces the experimental path on/off for tests. Production
    uses text-first unless FOUNDATIONHUB_WEB_GUI is set and a display exists.
    """
    if online is None:
        online = session.check_network()
    if not online:
        return LaunchPlan(
            None,
            "NO NETWORK — connect ethernet or enable WiFi in SETTINGS → NETWORK",
            "none",
        )

    # Supported path: text browser in the Hub's terminal (q to quit → back).
    text_argv = _pick_text(which)
    if text_argv is not None:
        # Only skip text when tests/operator force pure-gui selection.
        if gui is not True:
            return LaunchPlan(text_argv, None, "text")

    # Experimental GUI: opt-in env (or gui=True in tests) + display + binary.
    if gui is None:
        want_gui = gui_opted_in(env) and display_available(env)
    else:
        want_gui = bool(gui)

    if want_gui:
        gui_argv = _pick_gui(which)
        if gui_argv is not None:
            return LaunchPlan(gui_argv, None, "gui")

    if text_argv is not None:
        return LaunchPlan(text_argv, None, "text")

    if want_gui:
        return LaunchPlan(
            None,
            "NO BROWSER — install w3m (text) or firefox (experimental GUI)",
            "none",
        )
    return LaunchPlan(
        None,
        "NO TEXT BROWSER — install w3m (package: w3m)",
        "none",
    )


def status_hint(*,
                online: Optional[bool] = None,
                gui: Optional[bool] = None,
                which: Callable[[str], Optional[str]] = shutil.which,
                env: Optional[dict] = None) -> str:
    """Short right-hand hint for the Programs menu row."""
    if online is None:
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
