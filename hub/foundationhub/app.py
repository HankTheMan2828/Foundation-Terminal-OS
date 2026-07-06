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
from dataclasses import dataclass
from typing import Optional

from . import activity
from . import theme
from . import ui
from . import labels

POP = object()
QUIT = object()


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
        while self.stack:
            screen = self.stack[-1]
            screen.render(self.stdscr)
            if self.status_message:
                ui.draw_statusbar(self.stdscr, self.status_message, warn=True)
                self.stdscr.noutrefresh()
            curses.doupdate()
            try:
                key = self.stdscr.getch()
            except KeyboardInterrupt:
                key = -1
            self.status_message = ""
            action = screen.handle_key(key, self)
            self._dispatch(action)

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
