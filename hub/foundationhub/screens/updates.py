"""Settings > SYSTEM UPDATE (docs/UPDATE-SYSTEM.md §5) — the network update
path's operator surface, plus the transport-policy setting.

Everything is on demand: the release check is one HTTPS GET when CHECK is
pressed, and nothing here (or anywhere) polls in the background. Applying an
update and changing the policy are technician work — gated here by tier +
setup code for UX, re-verified authoritatively by the root helper
(pkexec foundation-update)."""
from __future__ import annotations

import curses

from .. import labels, session, theme, updates
from ..accounts import Tier
from ..app import POP, Screen
from ..ui import KEYS_BACK, LineEdit, Menu, MenuItem


def _is_technician() -> bool:
    acct = session.get_active_account()
    return acct is not None and acct.tier == Tier.TECHNICIAN


class UpdateScreen(Screen):
    title = labels.UPDATE
    subtitle = labels.UPDATE_SUBTITLE

    _MAIN, _POLICY, _CODE = range(3)

    def __init__(self):
        self.release = updates.current_release()
        self.mode = self._MAIN
        self.latest = ""            # tag from the last CHECK, "" = not checked
        self.message = ""
        self.edit = LineEdit(mask=True, limit=16)
        self._pending = None        # ("apply",) or ("policy", mode)
        self.menu = Menu(self._build())

    # ── menu building ─────────────────────────────────────────────────────────
    def _build(self) -> list[MenuItem]:
        if self.mode == self._POLICY:
            rows = [MenuItem(f"— {labels.UPDATE_POLICY} —", enabled=False),
                    MenuItem("", enabled=False)]
            current = updates.policy()
            for m in updates.POLICY_MODES:
                marker = "  ◄ current" if m == current else ""
                rows.append(MenuItem(f"{updates.policy_label(m)}{marker}",
                                     lambda a, m=m: self._gate(("policy", m))))
            return rows
        rows = [
            MenuItem(labels.UPDATE_CHECK, lambda a: self._check(),
                     hint="one request, only when asked"),
        ]
        if self.latest and updates.is_newer(self.latest,
                                            self.release["version"]):
            rows.append(MenuItem(f"{labels.UPDATE_APPLY} — {self.latest}",
                                 lambda a: self._gate(("apply",)),
                                 hint="takes minutes; screen may sit still"))
        rows.append(MenuItem(labels.UPDATE_POLICY,
                             lambda a: self._to_policy(),
                             status=updates.policy_label))
        return rows

    def _rebuild(self) -> None:
        index = self.menu.index
        self.menu = Menu(self._build())
        self.menu.set_index(index)

    # ── actions ───────────────────────────────────────────────────────────────
    def _check(self):
        err = updates.transport_check()
        if err:
            self.message = err.upper()
            return None
        tag, err = updates.check_latest()
        if err:
            self.message = err.upper()
            return None
        self.latest = tag
        if updates.is_newer(tag, self.release["version"]):
            self.message = f"{labels.UPDATE_AVAILABLE}: {tag}"
        else:
            self.message = f"{labels.UPDATE_UP_TO_DATE} ({tag})"
        self._rebuild()
        return None

    def _to_policy(self):
        self.mode = self._POLICY
        self._rebuild()
        return None

    def _gate(self, pending: tuple):
        """Technician tier first, then the setup-code prompt. The root helper
        re-verifies the code — this gate is UX, not the security boundary."""
        if not _is_technician():
            self.message = labels.UPDATE_TECH_ONLY
            return None
        self._pending = pending
        self.edit = LineEdit(mask=True, limit=16)
        self.mode = self._CODE
        return None

    def _run_pending(self, code: str):
        pending, self._pending = self._pending, None
        if pending == ("apply",):
            err = updates.apply_update(code)
            self.message = (err or labels.UPDATE_DONE).upper()
        elif pending and pending[0] == "policy":
            err = updates.set_policy(pending[1], code)
            self.message = (err or f"POLICY -> {updates.policy_label(pending[1])}").upper()
        self.mode = self._MAIN
        self._rebuild()
        return None

    # ── drawing ───────────────────────────────────────────────────────────────
    def draw(self, win, top: int, left: int) -> None:
        row = top
        try:
            win.addstr(row, left, labels.UPDATE_VERSION_HEADING,
                       theme.attr(theme.PAIR_DIM, dim=True))
            row += 1
            ver = self.release["version"]
            built = self.release["built"]
            win.addstr(row, left, f"{ver}" + (f"   built {built}" if built else ""),
                       theme.attr(theme.PAIR_NORMAL))
            row += 2

            self.menu.draw(win, row, left)

            h, w = win.getmaxyx()
            prompt_row = h - 4
            if self.mode == self._CODE:
                win.addstr(prompt_row, left,
                           f"{labels.UPDATE_CODE_PROMPT} {self.edit.display()}"
                           [: w - left - 2],
                           theme.attr(theme.PAIR_ACCENT, bold=True))
            elif self.message:
                win.addstr(prompt_row, left, self.message[: w - left - 2],
                           theme.attr(theme.PAIR_WARN, bold=True))
            elif updates.policy() == "usb":
                win.addstr(prompt_row, left,
                           labels.UPDATE_USB_HINT[: w - left - 2],
                           theme.attr(theme.PAIR_DIM, dim=True))
        except curses.error:
            pass

    def status_text(self):
        if self.mode == self._CODE:
            return labels.REG_HINT
        return labels.HINT_NAV

    # ── input ─────────────────────────────────────────────────────────────────
    def handle_key(self, key, app):
        if self.mode == self._CODE:
            result = self.edit.handle(key)
            if result == "cancel":
                self.mode = self._MAIN
                self._pending = None
                self._rebuild()
                return None
            if result == "submit":
                code = self.edit.value
                self.message = labels.UPDATE_APPLYING
                return self._run_pending(code)
            return None
        self.message = ""
        result = self.menu.handle_key(key, app)
        if result is not None:
            return result
        if key in KEYS_BACK:
            if self.mode == self._POLICY:
                self.mode = self._MAIN
                self._rebuild()
                return None
            return POP
        return None


def screen():
    return UpdateScreen()
