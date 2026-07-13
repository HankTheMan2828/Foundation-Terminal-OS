"""App core: the screen stack, main loop, input dispatch, external launches.

The Home Hub is a stack of Screens. Handlers return navigation *actions*:

    None            -> stay
    POP             -> go back one screen  (Esc/Backspace)
    QUIT            -> exit the Hub -> logs out the session (spec §4)
    LOGOUT          -> tear down to the login roster (session lock / power)
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
LOGOUT = object()   # return to the users/login page without killing the process


def _web_launch_status(log_path: str, returncode: int) -> str:
    """Short status-bar line from foundationhub-web's diagnostic log.

    Returns "" when there is nothing worth telling the operator: a clean exit
    where the wrapper never fell back to a text browser. A clean exit that DID
    fall back still reports — a silent w3m session reads as "the browser is
    text-only" instead of "the GUI failed, and here's where the log is".
    Earlier ERROR lines from attempts a later path recovered from are ignored
    on a clean, non-fallback exit.
    """
    last_err = ""
    fell_back = False
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if "falling back" in s.lower() or "fallback:" in s.lower():
                    fell_back = True
                    last_err = s
                elif "ERROR:" in s or "FAIL" in s:
                    last_err = s
    except OSError:
        pass
    clean = returncode in (0, None)
    if clean and not fell_back:
        return ""
    if last_err:
        # Strip leading timestamps so the bar stays readable on 80 cols.
        parts = last_err.split("ERROR:", 1)
        msg = parts[-1].strip() if len(parts) > 1 else last_err
        if len(msg) > 72:
            msg = msg[:69] + "..."
        return msg
    return f"WEB ACCESS exited ({returncode}) — see foundationhub-web.log"


# How long getch() blocks before the loop wakes on its own (ms). Without a
# timeout the loop only wakes on a keypress, so a Frank warning or the
# harm-to-user care message — produced asynchronously by frankd — would never
# surface while the operator sits on a screen. Waking ~2x/sec is imperceptible
# on a menu and lets Frank's messages appear within ~1s.
_FRANK_POLL_MS = 500
# Don't hammer the socket every wake — poll Frank at most this often (seconds).
_FRANK_POLL_INTERVAL = 1.0
# Infractions (and lockout copy) stay un-clearable for this long so the operator
# cannot key away before reading what Frank said.
_INFRACTION_HOLD_S = 2.0


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
        self.status_message = ""     # transient line (care messages only now)
        # Frank produces warnings and the harm-to-user care message asynchronously
        # and queues them; the Hub has to POLL to display them (read-only IPC —
        # this grants the Hub no power over Frank, spec §6). Missing this poll was
        # why warns/the self-harm care line never appeared. Reachable only on the
        # installed OS; off-device the client's socket connect just fails and
        # poll() returns None, so this is a no-op in the dev preview.
        self.frank = session.FrankClient()
        self._last_frank_poll = 0.0
        self._status_warn = True     # care lines render calm; residual status alarms
        # Once a lockout full-screen is up we avoid re-pushing every poll tick.
        self._lockout_active = False

    # -- navigation helpers usable from screens --
    def push(self, screen: Screen) -> None:
        # Report the navigation to Frank (report-only; see activity.py). This is
        # the "screen the user opened" half of "everything the user does".
        activity.record("screen", getattr(screen, "title", ""))
        self.stack.append(screen)

    def pop(self) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    def logout_to_login(self, notice: str = "") -> None:
        """Tear the logical session down and land on the users/login roster.

        Used by session-scope lockouts (and anything else that must return to
        the account list without exiting the foundationhub process).
        """
        session.set_active_account(None)
        self.status_message = ""
        self._lockout_active = False
        from .screens.login import LoginScreen
        self.stack[:] = [LoginScreen(notice=notice or labels.LOGIN_LOCKOUT_NOTICE)]

    # -- external programs --
    def launch(self, launch: Launch) -> None:
        import os
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
            env = os.environ.copy()
            # Web Access writes a diagnostic log; surface the last ERROR line if
            # the session dies immediately (one-frame flash / seat failure).
            web_log = None
            base = os.path.basename(exe)
            if base == "foundationhub-web" or exe.endswith("foundationhub-web"):
                # Persistent, so the evidence survives the reboot a stuck
                # console forces. Keep in sync with the wrapper's default.
                state = env.get("XDG_STATE_HOME") or os.path.join(
                    os.path.expanduser("~"), ".local", "state")
                web_log = os.path.join(state, "foundationhub-web.log")
                env["FOUNDATIONHUB_WEB_LOG"] = web_log
            result = subprocess.run(launch.argv, env=env)
            if web_log:
                note = _web_launch_status(web_log, result.returncode)
                if note:
                    self.status_message = note
        except Exception as exc:  # keep the Hub alive no matter what a child does
            self.status_message = f"launch failed: {exc}"
        finally:
            # Order matters. A child curses program resets the console palette on
            # exit, and ncurses resuming color mode here re-emits the `oc`
            # (orig_colors / \e]R "reset palette") capability on its first
            # refresh — so the palette retune must be the LAST thing written, or
            # that refresh wipes our amber straight back to stock green.
            curses.reset_prog_mode()
            self.stdscr.refresh()
            theme.dress_console()

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
            # Self-heal the VT palette every frame, immediately AFTER the update
            # that could have emitted `oc` (ncurses' palette reset). Cheap and
            # idempotent — the same phosphor RGBs are already on screen — and it
            # means no reset path (startup color-init, resume from a child) can
            # leave the amber/accent slots stuck on stock hues. Mirrors the
            # frame-by-frame background re-assert in ui.draw_chrome.
            theme.dress_console()
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

    def _frank_msg_for_active(self, msg: dict) -> bool:
        """Multi-user isolation: only surface Frank lines meant for this account.

        frankd already filters the poll queue, but the Hub double-checks so a
        stale or mis-routed session warn/lockout for Alice can never interrupt
        Bob (docs/USERS.md). Machine-scope lockouts still apply to whoever is
        signed in. With no active account (login roster), only machine lockouts
        are considered — and those are gated by login.locks, so we drop them
        here to avoid banner spam on the greeter.
        """
        mtype = msg.get("type", "")
        acct = session.get_active_account()
        if mtype == "lockout" and str(msg.get("scope", "")) == "machine":
            return acct is not None
        if acct is None:
            return False
        user = (msg.get("user") or "").strip()
        if not user:
            return True
        return user == acct.username

    def _poll_frank(self) -> None:
        """Ask frankd if there's a warning / care line / lockout to DISPLAY.

        Read-only — the Hub can only reflect what Frank decides (spec §6).
        Throttled, and a no-op when Frank isn't reachable (dev preview).
        """
        now = time.monotonic()
        if now - self._last_frank_poll < _FRANK_POLL_INTERVAL:
            return
        self._last_frank_poll = now
        msg = self.frank.poll()
        if not msg or msg.get("type") == "NONE":
            return
        mtype = msg.get("type", "")
        if mtype in ("warn", "lockout", "care") and not self._frank_msg_for_active(msg):
            return
        if mtype == "care":
            raw = msg.get("raw", "")
            text = msg.get("msg") or raw.partition("msg=")[2].strip() or raw
            self.status_message = text
            self._status_warn = False
            return
        if mtype == "warn":
            self._show_infraction_banner(msg)
            return
        if mtype == "lockout":
            self._handle_lockout_message(msg)
            return
        # Unknown type: fall back to a status line so nothing is silently lost.
        raw = msg.get("raw", "")
        text = msg.get("msg") or raw.partition("msg=")[2].strip() or raw
        self.status_message = text
        self._status_warn = True

    def _show_infraction_banner(self, msg: dict) -> None:
        """Full-screen infraction notice; clearable only after 2 seconds.

        Replaces the old one-line status-bar delivery so the operator cannot
        key past a violation without seeing what it was.
        """
        text = (msg.get("msg") or "").strip() or "Infraction recorded."
        # Scrub the trip string so the same content cannot re-fire after
        # the operator continues (or after a lockout expires).
        self._scrub_infraction(msg)
        lines = [
            labels.INFRACTION_TITLE,
            "",
            *self._wrap_msg(text, 60),
            "",
            labels.INFRACTION_HOLD,
        ]
        self._blocking_banner(lines, min_seconds=_INFRACTION_HOLD_S)

    def _handle_lockout_message(self, msg: dict) -> None:
        """Immediate lockout: full screen, redact source file, then logout.

        Session locks always end on the users/login page. If negotiation is
        available, the banner says so and offers N before accepting logout.
        Machine locks are also shown (root enforcer still owns the VT on
        hardware); the Hub still tears the logical session down.
        """
        if session.get_active_account() is None and not self._lockout_active:
            # Already on the login roster — continuous lock status is reflected
            # there via login.locks; don't re-banner every poll.
            return
        if self._lockout_active:
            return

        self._scrub_infraction(msg)

        self._lockout_active = True
        negotiable = str(msg.get("negotiable", "0")) == "1"
        remaining = self._parse_remaining(msg)

        while self._lockout_active:
            lines = self._lockout_lines(msg, negotiable=negotiable,
                                        remaining=remaining)
            accept_keys = {ord("\n"), ord("\r"), curses.KEY_ENTER, ord(" ")}
            extra = {ord("n"), ord("N")} if negotiable else set()
            key = self._blocking_banner(
                lines, min_seconds=_INFRACTION_HOLD_S,
                accept_keys=accept_keys | extra | {27})
            if negotiable and key in (ord("n"), ord("N")):
                released = self._run_negotiate()
                if released:
                    self._lockout_active = False
                    return
                # Re-check remaining / negotiable after a denied or shortened plea.
                follow = self.frank.poll()
                if follow and follow.get("type") == "lockout":
                    msg = follow
                    negotiable = str(msg.get("negotiable", "0")) == "1"
                    remaining = self._parse_remaining(msg)
                elif follow and follow.get("type") == "NONE":
                    self._lockout_active = False
                    return
                continue
            break

        self.logout_to_login(labels.LOGIN_LOCKOUT_NOTICE)

    def _lockout_lines(self, msg: dict, *, negotiable: bool,
                       remaining: int) -> list[str]:
        text = (msg.get("msg") or "").strip() or "Access to this console is suspended."
        mmss = f"{max(0, remaining) // 60:02d}:{max(0, remaining) % 60:02d}"
        lines = [
            labels.LOCKOUT_TITLE,
            "",
            *self._wrap_msg(text, 60),
            "",
            labels.LOCKOUT_REMAINING.format(mmss=mmss),
            "",
        ]
        if negotiable:
            lines.append(labels.LOCKOUT_NEGOTIABLE)
            lines.append(labels.LOCKOUT_NEGOTIABLE_HOW)
        else:
            lines.append(labels.LOCKOUT_NOT_NEGOTIABLE)
        lines.append("")
        lines.append(labels.LOCKOUT_ACCEPT)
        lines.append(labels.LOCKOUT_HOLD)
        return lines

    def _run_negotiate(self) -> bool:
        """Push the negotiate screen as a modal loop. True if lock was lifted."""
        from .screens.negotiate import NegotiateScreen
        screen = NegotiateScreen(client=self.frank)
        # Don't report this navigation as ordinary activity mid-lockout.
        self.stack.append(screen)
        released = False
        try:
            while self.stack and self.stack[-1] is screen:
                screen.render(self.stdscr)
                curses.doupdate()
                theme.dress_console()
                try:
                    key = self.stdscr.getch()
                except KeyboardInterrupt:
                    key = 27
                if key == -1:
                    continue
                action = screen.handle_key(key, self)
                if action is POP:
                    self.stack.pop()
                    break
                # NegotiateScreen returns POP on "released"; also detect via
                # a fresh poll in case the screen only cleared its message.
            # After leaving negotiate, see if the lock is gone.
            follow = self.frank.poll()
            if follow is None or follow.get("type") == "NONE":
                released = True
            elif follow.get("type") == "lockout":
                remaining = self._parse_remaining(follow)
                released = remaining <= 0
            # If the screen popped itself because outcome=released:
            if getattr(screen, "_released", False):
                released = True
        finally:
            while self.stack and self.stack[-1] is screen:
                self.stack.pop()
        return released

    def _scrub_infraction(self, msg: dict) -> None:
        """Replace the trip string with *** everywhere it could re-fire.

        Covers the last saved content file, any open editor buffers, the
        activity spool (so a frankd restart cannot re-classify the line),
        and AI chat transcript/history still on the screen stack.
        """
        matched = (msg.get("matched") or "").strip()
        if not matched:
            return
        session.redact_infraction_in_file(matched)
        session.redact_infraction_in_activity(matched)
        self._redact_open_editor(matched)
        self._redact_open_chat(matched)

    def _redact_open_editor(self, matched: str) -> None:
        """Redact `matched` in every open editor buffer on the stack."""
        if not matched:
            return
        for scr in self.stack:
            editor = getattr(scr, "editor", None) or scr
            buf = getattr(editor, "buffer", None)
            if buf is None:
                continue
            try:
                text = buf.text()
                new = session.redact_matched_in_text(text, matched)
                if new != text:
                    buf.lines = new.split("\n") if new else [""]
                    buf.dirty = True
            except Exception:
                pass

    def _redact_open_chat(self, matched: str) -> None:
        """Redact `matched` in any open AI chat transcript/history."""
        if not matched:
            return
        for scr in self.stack:
            transcript = getattr(scr, "transcript", None)
            history = getattr(scr, "history", None)
            if transcript is not None:
                try:
                    scr.transcript = [
                        (speaker, session.redact_matched_in_text(text, matched))
                        for speaker, text in transcript
                    ]
                except Exception:
                    pass
            if history is not None:
                try:
                    for turn in history:
                        if isinstance(turn, dict) and "content" in turn:
                            turn["content"] = session.redact_matched_in_text(
                                str(turn["content"]), matched)
                except Exception:
                    pass

    def _blocking_banner(self, lines: list[str], *, min_seconds: float,
                         accept_keys: set[int] | None = None) -> int:
        """Paint a full-screen banner; ignore keys until min_seconds elapses.

        Returns the key that dismissed it, or -1 if the hold elapsed with no
        further key (caller may treat any post-hold key, including -1 timeout
        after hold, as they wish — we wait for a real key after the hold).
        """
        clearable_at = time.monotonic() + min_seconds
        self.stdscr.timeout(100)
        key = -1
        while True:
            ui.full_screen_banner(self.stdscr, lines, alert=True)
            curses.doupdate()
            theme.dress_console()
            try:
                key = self.stdscr.getch()
            except KeyboardInterrupt:
                key = 27
            now = time.monotonic()
            if now < clearable_at:
                continue
            if key == -1:
                continue
            if accept_keys is not None and key not in accept_keys:
                # After hold, still only accept the keys the caller named
                # (lockout: Enter/N); for infractions accept_keys is None = any.
                continue
            break
        self.stdscr.timeout(_FRANK_POLL_MS)
        return key

    @staticmethod
    def _wrap_msg(text: str, width: int) -> list[str]:
        words = text.split()
        if not words:
            return [text]
        rows: list[str] = []
        cur = words[0]
        for w in words[1:]:
            if len(cur) + 1 + len(w) <= width:
                cur = f"{cur} {w}"
            else:
                rows.append(cur)
                cur = w
        rows.append(cur)
        return rows

    @staticmethod
    def _parse_remaining(msg: dict) -> int:
        try:
            return max(0, int(msg.get("remaining") or 0))
        except (TypeError, ValueError):
            return 0

    def _dispatch(self, action) -> None:
        if action is None:
            return
        if action is POP:
            self.pop()
        elif action is QUIT:
            self.stack.clear()
        elif action is LOGOUT:
            self.logout_to_login()
        elif isinstance(action, Launch):
            self.launch(action)
        elif isinstance(action, Screen):
            self.push(action)
        elif callable(action):
            action(self)
