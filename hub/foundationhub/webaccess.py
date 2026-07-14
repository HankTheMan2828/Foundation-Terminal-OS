"""Web Access — open DuckDuckGo in a real browser when possible.

Curses-free launch planner used by Programs → WEB ACCESS.

Preferred path (operator request 2026-07-13):
  **Firefox** inside a temporary **sway** kiosk session, launched via the
  `foundationhub-web` wrapper. That wrapper always returns to the Hub when
  Firefox exits (Ctrl+Q or close window), and provides **keyboard pointer**
  control until a real mouse is wired system-wide:

    Alt+arrows       move pointer
    Alt+Shift+arrows fine move
    Alt+Enter        left click
    Alt+Backspace    right click
    Ctrl+Q           quit session → back to Programs

Fallback:
  Text browser (w3m / lynx / links / elinks) in the Hub terminal — same as
  the pre-Firefox path. Used only when the GUI stack is not installed.

Why not bare `firefox` on the VT:
  Auto-picking a graphical browser without a session manager left the
  operator unable to type or exit (v0.1.1 hardware report). The wrapper is
  the verified entry/exit contract.

General connectivity (ethernet or WiFi) is enough; not gated by the
system-update wireless policy.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from . import network as netmod
from . import session

# DuckDuckGo — full site for Firefox; HTML endpoint for text browsers.
DDG_HOME = "https://duckduckgo.com"
DDG_HTML = "https://html.duckduckgo.com/html/"

# Wrapper installed by install/04-hub.sh from system/usr/local/bin/.
_WEB_WRAPPER = "foundationhub-web"

# Pieces the wrapper needs if someone invokes a degraded path.
_FIREFOX_BINS: Sequence[str] = (
    "firefox",
    "firefox-esr",
)
_SWAY_BIN = "sway"

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
    """True when a graphical session looks reachable (X11 or Wayland).

    Kept for tests/diagnostics. The Firefox path does **not** require a
    pre-existing display — foundationhub-web starts its own sway session.
    """
    e = env if env is not None else os.environ
    if e.get("WAYLAND_DISPLAY") or e.get("DISPLAY"):
        return True
    return os.path.isdir("/tmp/.X11-unix")


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


def gui_stack_ready(which: Callable[[str], Optional[str]] = shutil.which) -> bool:
    """True when the Firefox kiosk path can run (wrapper, or firefox+sway)."""
    if which(_WEB_WRAPPER):
        return True
    return bool(which_first(_FIREFOX_BINS, which) and which(_SWAY_BIN))


def _pick_gui(which: Callable[[str], Optional[str]],
              url: str = DDG_HOME) -> Optional[list[str]]:
    """Prefer the install wrapper; otherwise firefox+sway is incomplete without
    it (no pointer binds / exit contract), so only the wrapper is returned as
    a ready argv. Callers may still detect firefox presence for messaging.
    """
    if which(_WEB_WRAPPER):
        return [_WEB_WRAPPER, url]
    return None


def plan_launch(*,
                online: Optional[bool] = None,
                gui: Optional[bool] = None,
                which: Callable[[str], Optional[str]] = shutil.which,
                env: Optional[dict] = None,
                url: str = DDG_HOME) -> LaunchPlan:
    """Decide how to open Web Access. All IO is injectable for tests.

    Preference order:
      1. Firefox via foundationhub-web (real browser + keyboard pointer)
      2. Text browser (w3m/…) in the Hub terminal
      3. Clear not-installed message

    `gui` when False forces text-only (tests / emergency). When True, refuse
    to fall back to text if the GUI stack is missing.
    """
    del env  # reserved for future display/env gates; wrapper owns the session
    if online is None:
        online = session.check_network()
    if not online:
        return LaunchPlan(
            None,
            "NO NETWORK — connect ethernet or enable WiFi in SETTINGS → NETWORK",
            "none",
        )

    force_text = gui is False
    force_gui = gui is True

    if not force_text:
        gui_argv = _pick_gui(which, url=url)
        if gui_argv is not None:
            return LaunchPlan(gui_argv, None, "gui")
        if force_gui:
            ff = which_first(_FIREFOX_BINS, which)
            if not ff and not which(_SWAY_BIN):
                return LaunchPlan(
                    None,
                    "NO BROWSER — install firefox + sway (see install/packages.txt)",
                    "none",
                )
            if not ff:
                return LaunchPlan(
                    None,
                    "NO FIREFOX — install package: firefox",
                    "none",
                )
            if not which(_SWAY_BIN):
                return LaunchPlan(
                    None,
                    "NO COMPOSITOR — install package: sway (Web Access kiosk)",
                    "none",
                )
            return LaunchPlan(
                None,
                "NO WEB LAUNCHER — install foundationhub-web (re-run install/04)",
                "none",
            )

    text_argv = _pick_text(which)
    if text_argv is not None:
        return LaunchPlan(text_argv, None, "text")

    if gui_stack_ready(which) is False and which_first(_FIREFOX_BINS, which):
        # Firefox on disk but no wrapper/sway — tell them what to install.
        return LaunchPlan(
            None,
            "FIREFOX FOUND BUT WEB KIOSK INCOMPLETE — install sway + re-run install/04",
            "none",
        )

    return LaunchPlan(
        None,
        "NO BROWSER — install firefox (and sway) or w3m; see install/packages.txt",
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
        return "Firefox · Alt+arrows pointer · Ctrl+Q quit"
    if plan.mode == "text":
        return "text browser · q quit"
    return "no browser"


def connectivity_summary() -> str:
    """One-line network status for a pre-launch screen / message."""
    return netmod.network_status().summary


def web_log_path(env: Optional[dict] = None) -> str:
    """The persistent foundationhub-web diagnostic log.

    Keep in sync with the wrapper's default and app.launch(): XDG state dir,
    NOT /run/user — it must survive the reboot a stuck console forces.
    """
    e = env if env is not None else os.environ
    state = e.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state")
    return os.path.join(state, "foundationhub-web.log")


def read_web_log(limit: int = 500, env: Optional[dict] = None) -> list[str]:
    """Last `limit` lines of the web diagnostic log; [] if none. Never raises."""
    try:
        with open(web_log_path(env), "r", encoding="utf-8",
                  errors="replace") as fh:
            lines = [ln.rstrip("\n") for ln in fh]
    except OSError:
        return []
    return lines[-limit:]
