"""App core: the screen stack, main loop, input dispatch, external launches.

The Home Hub is a stack of Screens. Handlers return navigation *actions*:

    None            -> stay
    POP             -> go back one screen  (Esc/Backspace)
    QUIT            -> exit the Hub -> logs out the session (spec §4)
    a Screen        -> push it
    Launch(argv)    -> suspend curses, run an external program, resume

Keeping navigation declarative keeps screens simple and testable.
"""
from __future__ import annotations

import curses
import time
from dataclasses import dataclass
from typing import Optional

from . import activity
from . import session
from . import theme
from . import ui
from . import labels

POP = object()
QUIT = object()

# How long getch() blocks before the loop wakes on its own (ms). Without a
# timeout the loop only wakes on a keypress, so a Frank warning or the
# harm-to-user care message — produced asynchronously by frankd — would never
# surface while the operator sits on a screen. Waking ~2x/sec is imperceptible
# on a menu and lets Frank's messages appear within ~1s.
_FRANK_POLL_MS = 500
# Don't hammer the socket every wake — poll Frank at most this often (seconds).
_FRANK_POLL_INTERVAL = 1.0


@dataclass
class Launch:
    """Suspend the TUI and run an external program (ranger, btop, a game…)."""
    argv: list[str]
    missing_hint: str = labels.NOT_INSTALLED


class Screen:
    """Base screen. Subclass and override draw()/handle_key(), or use MenuScreen."""

    title = labels.HUB_TITLE
    subtitle = ""

    def render(self, win) -> None:
        top, left = ui.draw_chrome(win, self.title, self.subtitle)
        self.draw(win, top, left)
        ui.draw_statusbar(win, self.status_text())
        win.noutrefresh()

    def draw(self, win, top: int, left: int) -> None:  # pragma: no cover - visual
        ...

    def status_text(self) -> str:
        return labels.HINT_NAV

    def handle_key(self, key: int, app) -> object:
        if key in ui.KEYS_BACK:
            return POP
        return None


class MenuScreen(Screen):
    """A screen whose body is a single Menu. The common case."""

    def __init__(self, title: str, items: list[ui.MenuItem], *, subtitle: str = "",
                 status: Optional[str] = None):
        self.title = title
        self.subtitle = subtitle
        self.menu = ui.Menu(items)
        self._status = status

    def draw(self, win, top: int, left: int) -> None:
        self.menu.draw(win, top, left)

    def status_text(self) -> str:
        return self._status or labels.HINT_NAV

    def handle_key(self, key: int, app) -> object:
        result = self.menu.handle_key(key, app)
        if result is not None:
            return result
        if key in ui.KEYS_BACK:
            return POP
        return None


class App:
    """Owns the curses window, the screen stack, and the run loop."""

    def __init__(self, stdscr, root_factory):
        self.stdscr = stdscr
        self.stack: list[Screen] = [root_factory(self)]
        self.status_message = ""     # transient line (e.g. Frank status-bar warns)
        # Frank produces warnings and the harm-to-user care message asynchronously
        # and queues them; the Hub has to POLL to display them (read-only IPC —
        # this grants the Hub no power over Frank, spec §6). Missing this poll was
        # why warns/the self-harm care line never appeared. Reachable only on the
        # installed OS; off-device the client's socket connect just fails and
        # poll() returns None, so this is a no-op in the dev preview.
        self.frank = session.FrankClient()
        self._last_frank_poll = 0.0
        self._status_warn = True     # care lines render calm; warns/locks alarm

    # -- navigation helpers usable from screens --
    def push(self, screen: Screen) -> None:
        # Report the navigation to Frank (report-only; see activity.py). This is
        # the "screen the user opened" half of "everything the user does".
        activity.record("screen", getattr(screen, "title", ""))
        self.stack.append(screen)

    def pop(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    # -- external programs --
    def launch(self, launch: Launch) -> None:
        import shutil
        import subprocess

        exe = launch.argv[0]
        if shutil.which(exe) is None:
            self.status_message = f"{exe} {launch.missing_hint}"
            return
        # The program the user started — reported to Frank before we hand the
        # console over to the child (report-only; see activity.py).
        activity.record("launch", " ".join(launch.argv))
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.run(launch.argv)
        except Exception as exc:  # keep the Hub alive no matter what a child does
            self.status_message = f"launch failed: {exc}"
        finally:
            curses.reset_prog_mode()
            self.stdscr.refresh()

    # -- main loop --
    def run(self) -> None:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        # Wake on our own every _FRANK_POLL_MS even without input, so Frank's
        # warnings / care message surface promptly instead of only on a keypress.
        self.stdscr.timeout(_FRANK_POLL_MS)
        while self.stack:
            screen = self.stack[-1]
            screen.render(self.stdscr)
            self._poll_frank()
            if self.status_message:
                ui.draw_statusbar(self.stdscr, self.status_message,
                                  warn=self._status_warn)
                self.stdscr.noutrefresh()
            curses.doupdate()
            try:
                key = self.stdscr.getch()
            except KeyboardInterrupt:
                key = -1
            if key == -1:
                # Timeout wake, no input: keep any Frank message on screen and
                # loop (so it doesn't get cleared before the user ever sees it).
                continue
            self.status_message = ""
            self._status_warn = True
            action = screen.handle_key(key, self)
            self._dispatch(action)

    def _poll_frank(self) -> None:
        """Ask frankd if there's a warning / care line to DISPLAY. Read-only —
        the Hub can only reflect what Frank decides (spec §6). Throttled, and a
        no-op when Frank isn't reachable (dev preview / not installed)."""
        now = time.monotonic()
        if now - self._last_frank_poll < _FRANK_POLL_INTERVAL:
            return
        self._last_frank_poll = now
        msg = self.frank.poll()
        if not msg or msg.get("type") == "NONE":
            return
        raw = msg.get("raw", "")
        # Protocol is "TYPE ... msg=<free text>"; show the human line if present.
        text = raw.partition("msg=")[2].strip()
        self.status_message = text or raw
        # The harm-to-user care line is supportive, not an alarm — render it calm.
        self._status_warn = msg.get("type") != "care"

    def _dispatch(self, action) -> None:
        if action is None:
            return
        if action is POP:
            self.pop()
        elif action is QUIT:
            self.stack.clear()
        elif isinstance(action, Launch):
            self.launch(action)
        elif isinstance(action, Screen):
            self.push(action)
        elif callable(action):
            action(self)
