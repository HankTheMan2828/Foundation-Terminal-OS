"""System Status (spec §5) — was CONFIGURATION.

Read-only now (feedback #8): NETWORK config moved to Settings, and Status is
reached from inside Settings rather than the top level. What's left is a pure
readout — who's logged in, and whether the basics are up. Resource limits and
user/auth actions remain gone at the user's explicit direction.
"""
from __future__ import annotations

import curses

from .. import labels, session, theme, updates
from ..app import POP, Screen
from ..ui import KEYS_BACK


class StatusScreen(Screen):
    title = labels.STATUS
    subtitle = "read-only readout"

    def __init__(self):
        self._user, self._uid = session.get_user_identity()
        self._release = updates.current_release()
        self._checks = [
            (labels.STATUS_CHECK_NETWORK, session.check_network),
            (labels.STATUS_CHECK_AUDIO, session.check_audio),
            (labels.STATUS_CHECK_FRANK, session.check_frank),
        ]

    def handle_key(self, key, app):
        if key in KEYS_BACK:
            return POP
        return None

    def draw(self, win, top: int, left: int) -> None:
        row = top
        try:
            win.addstr(row, left, labels.STATUS_USER_HEADING,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
            win.addstr(row, left, f"{self._user}   uid {self._uid}",
                       theme.attr(theme.PAIR_NORMAL))
            row += 1
            acct = session.get_active_account()
            if acct is not None:
                from ..accounts import GiB, MiB
                q = acct.info.quota_bytes
                quota = (f"{q // GiB} GB" if q >= GiB else f"{q // MiB} MB")
                win.addstr(row, left,
                           f"{acct.info.label}   allotment {quota}",
                           theme.attr(theme.PAIR_NORMAL))
                row += 1
            row += 1

            # Version identity (docs/UPDATE-SYSTEM.md §2) — what this machine
            # runs, from /etc/foundation-release.
            win.addstr(row, left, labels.UPDATE_VERSION_HEADING,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
            built = self._release["built"]
            win.addstr(row, left,
                       self._release["version"] + (f"   built {built}" if built else ""),
                       theme.attr(theme.PAIR_NORMAL))
            row += 2

            win.addstr(row, left, labels.STATUS_FUNCTIONS_HEADING,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
            for label, check in self._checks:
                ok = check()
                state = labels.STATUS_FUNCTIONING if ok else labels.STATUS_NOT_FUNCTIONING
                pair = theme.PAIR_NORMAL if ok else theme.PAIR_WARN
                win.addstr(row, left, f"{label:<24}{state}",
                           theme.attr(pair, bold=not ok))
                row += 1
                # When Frank is down, show WHY right under the line — the only
                # way to diagnose a dead overseer on a no-shell locked kiosk.
                if check is session.check_frank and not ok:
                    reason = session.frank_health()
                    if reason:
                        _, w = win.getmaxyx()
                        win.addstr(row, left + 2, f"↳ {reason}"[: w - left - 4],
                                   theme.attr(theme.PAIR_DIM, dim=True))
                        row += 1
        except curses.error:
            pass


def screen():
    return StatusScreen()
