"""Login — the terminal's front door (docs/USERS.md).

Shown before the Home Hub. Lists this machine's accounts (max 8), takes a
password, and hands the authenticated account to the session. Registration
is self-service for GUEST; every higher tier requires the technician setup
code — the placeholder for the future company user-ID system, which will
slot into RegistrationScreen as an extra identification step.

Frank is present here too: the screen refuses accounts that appear in the
overseer's public lock summary (usernames + expiry timestamps only), and a
machine-scope lock disables the whole roster. On the target the root locker
owns the console during a machine lock anyway; this is the belt to that
suspenders.
"""
from __future__ import annotations

import curses
import time

from .. import labels, session, theme
from ..accounts import (MAX_ACCOUNTS, Registry, RegistryError, Tier, TIERS,
                        GiB, MiB)
from ..app import MenuScreen, Screen, POP
from ..ui import Menu, MenuItem, KEYS_BACK, KEYS_SELECT
from . import build_home, power

_FAILS_BEFORE_COOLDOWN = 3
_COOLDOWN_SECONDS = 30

# Per-account failure state, survives screen pushes/pops within one greeter
# process: username -> {"fails": int, "until": epoch}.
_auth_state: dict[str, dict] = {}


def _fmt_quota(nbytes: int) -> str:
    if nbytes >= GiB:
        return f"{nbytes // GiB} GB"
    return f"{nbytes // MiB} MB"


def _fmt_remaining(end: float, now: float) -> str:
    left = max(0, int(end - now))
    return f"{left // 60:02d}:{left % 60:02d}"


def _start_session(app, acct) -> None:
    """Authenticated: the Hub replaces the login stack entirely."""
    session.set_active_account(acct)
    _auth_state.pop(acct.username, None)
    app.stack[:] = [build_home(app)]


class _LineEdit:
    """Minimal single-line editor for curses prompts. ASCII, bounded."""

    def __init__(self, *, mask: bool = False, limit: int = 32):
        self.value = ""
        self.mask = mask
        self.limit = limit

    def handle(self, key: int) -> str | None:
        """Returns "submit", "cancel", or None (keep editing)."""
        if key in KEYS_SELECT and key != ord(" "):
            return "submit"
        if key == 27:                      # Esc — cancel, never navigate-back
            return "cancel"
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.value = self.value[:-1]
        elif 32 <= key <= 126 and len(self.value) < self.limit:
            self.value += chr(key)
        return None

    def display(self) -> str:
        shown = "•" * len(self.value) if self.mask else self.value
        return shown + "_"


class PasswordScreen(Screen):
    """Password prompt for one account. 3 failures = a per-account cooldown."""

    subtitle = labels.LOGIN_SUBTITLE

    def __init__(self, acct, registry: Registry):
        self.acct = acct
        self.registry = registry
        self.title = labels.LOGIN_PASSWORD_FOR.format(user=acct.username)
        self.edit = _LineEdit(mask=True, limit=64)
        self.message = ""

    def _state(self) -> dict:
        return _auth_state.setdefault(self.acct.username,
                                      {"fails": 0, "until": 0.0})

    def draw(self, win, top, left):
        st = self._state()
        now = time.time()
        win.addstr(top, left, f"{labels.LOGIN_PASSWORD_PROMPT}:",
                   theme.attr(theme.PAIR_DIM, dim=True))
        win.addstr(top + 1, left, self.edit.display(),
                   theme.attr(theme.PAIR_NORMAL, bold=True))
        if now < st["until"]:
            msg = f"{labels.LOGIN_COOLDOWN} {_fmt_remaining(st['until'], now)}"
            win.addstr(top + 3, left, msg, theme.attr(theme.PAIR_WARN, bold=True))
        elif self.message:
            win.addstr(top + 3, left, self.message,
                       theme.attr(theme.PAIR_WARN, bold=True))

    def status_text(self):
        return labels.REG_HINT

    def handle_key(self, key, app):
        result = self.edit.handle(key)
        if result == "cancel":
            return POP
        if result != "submit":
            return None
        st = self._state()
        now = time.time()
        if now < st["until"]:
            return None   # cooldown active; the countdown is on screen
        acct = self.registry.verify_login(self.acct.username, self.edit.value)
        if acct is not None:
            return lambda a: _start_session(a, acct)
        st["fails"] += 1
        self.edit.value = ""
        self.message = labels.LOGIN_DENIED
        if st["fails"] >= _FAILS_BEFORE_COOLDOWN:
            st["fails"] = 0
            st["until"] = now + _COOLDOWN_SECONDS
        return None


class RegistrationScreen(Screen):
    """Stepped registration. GUEST is self-service; higher tiers demand the
    technician setup code (future: the company user-ID presentation step)."""

    title = labels.REG_TITLE
    subtitle = labels.LOGIN_SUBTITLE

    STEP_USERNAME, STEP_TIER, STEP_CODE, STEP_PASSWORD, STEP_CONFIRM = range(5)

    def __init__(self, registry: Registry):
        self.registry = registry
        self.step = self.STEP_USERNAME
        self.username = ""
        self.tier = Tier.GUEST
        self.setup_code = ""
        self.password = ""
        self.message = ""
        self.edit = _LineEdit(limit=16)
        self.tier_menu = Menu([
            MenuItem(TIERS[t].label,
                     (lambda tier: (lambda a: self._pick_tier(tier)))(t),
                     hint=_fmt_quota(TIERS[t].quota_bytes)
                          + ("" if not TIERS[t].needs_setup_code
                             else "   [setup code]"))
            for t in Tier
        ])

    # ── step transitions ─────────────────────────────────────────────────────
    def _goto(self, step: int, *, mask: bool, limit: int = 64) -> None:
        self.step = step
        self.edit = _LineEdit(mask=mask, limit=limit)

    def _pick_tier(self, tier: Tier):
        self.tier = tier
        self.message = ""
        if TIERS[tier].needs_setup_code:
            self._goto(self.STEP_CODE, mask=True, limit=16)
        else:
            self._goto(self.STEP_PASSWORD, mask=True)
        return None

    def _finish(self, app):
        try:
            self.registry.add_account(self.username, self.password, self.tier,
                                      setup_code=self.setup_code)
        except RegistryError as exc:
            if "not writable" in str(exc):
                err = _create_via_helper(self.username, self.password,
                                         self.tier, self.setup_code)
                if err is None:
                    app.stack[:] = [LoginScreen(notice=labels.REG_DONE)]
                    return
                exc = RegistryError(err)
            self.message = str(exc)
            if "setup code" in str(exc):
                self._goto(self.STEP_CODE, mask=True, limit=16)
            elif "password" in str(exc):
                self._goto(self.STEP_PASSWORD, mask=True)
            else:
                self._goto(self.STEP_USERNAME, mask=False, limit=16)
            return
        app.stack[:] = [LoginScreen(notice=labels.REG_DONE)]

    # ── rendering ────────────────────────────────────────────────────────────
    _PROMPTS = {
        STEP_USERNAME: labels.REG_USERNAME,
        STEP_CODE: labels.REG_SETUP_CODE,
        STEP_PASSWORD: labels.REG_PASSWORD,
        STEP_CONFIRM: labels.REG_PASSWORD_CONFIRM,
    }

    def draw(self, win, top, left):
        if self.username:
            win.addstr(top, left,
                       f"{labels.REG_USERNAME}: {self.username}   "
                       f"{labels.REG_TIER}: {TIERS[self.tier].label}",
                       theme.attr(theme.PAIR_DIM, dim=True))
        row = top + 2
        if self.step == self.STEP_TIER:
            win.addstr(row, left, f"{labels.REG_TIER}:",
                       theme.attr(theme.PAIR_DIM, dim=True))
            self.tier_menu.draw(win, row + 1, left)
        else:
            win.addstr(row, left, f"{self._PROMPTS[self.step]}:",
                       theme.attr(theme.PAIR_DIM, dim=True))
            win.addstr(row + 1, left, self.edit.display(),
                       theme.attr(theme.PAIR_NORMAL, bold=True))
        if self.message:
            win.addstr(row + 3, left, self.message,
                       theme.attr(theme.PAIR_WARN, bold=True))

    def status_text(self):
        return labels.REG_HINT

    # ── input ────────────────────────────────────────────────────────────────
    def handle_key(self, key, app):
        if self.step == self.STEP_TIER:
            if key in KEYS_BACK:
                return POP
            return self.tier_menu.handle_key(key, app)
        result = self.edit.handle(key)
        if result == "cancel":
            return POP
        if result != "submit":
            return None
        value = self.edit.value
        self.message = ""
        if self.step == self.STEP_USERNAME:
            self.username = value.strip().lower()
            self.step = self.STEP_TIER
        elif self.step == self.STEP_CODE:
            self.setup_code = value
            self._goto(self.STEP_PASSWORD, mask=True)
        elif self.step == self.STEP_PASSWORD:
            self.password = value
            if not value and self.tier is Tier.GUEST:
                self._finish(app)   # guests may go passwordless
            else:
                self._goto(self.STEP_CONFIRM, mask=True)
        elif self.step == self.STEP_CONFIRM:
            if value != self.password:
                self.message = labels.REG_MISMATCH
                self._goto(self.STEP_PASSWORD, mask=True)
            else:
                self._finish(app)
        return None


def _create_via_helper(username: str, password: str, tier: Tier,
                       setup_code: str) -> str | None:
    """Target path: the registry is root-owned, so creation goes through the
    root helper (pkexec zenhub-account). Returns an error string or None."""
    import shutil
    import subprocess
    if shutil.which("pkexec") is None:
        return "registration unavailable (no root helper on this machine)"
    try:
        res = subprocess.run(
            ["pkexec", "/usr/local/bin/zenhub-account", "create",
             username, str(int(tier))],
            input=f"{password}\n{setup_code}\n", text=True,
            capture_output=True, timeout=30)
    except Exception as exc:
        return f"registration failed: {exc}"
    if res.returncode != 0:
        return (res.stderr or res.stdout).strip() or "registration failed"
    return None


class LoginScreen(Screen):
    """The account roster. Locked accounts (per Frank's public summary) are
    disabled with a countdown; a machine lock disables everything."""

    title = labels.LOGIN_TITLE
    subtitle = labels.LOGIN_SUBTITLE

    def __init__(self, notice: str = ""):
        self.registry = Registry()
        self.notice = notice
        self._machine_locked_until = 0.0
        self._build_menu()

    def _build_menu(self) -> None:
        items = []
        for acct in self.registry.accounts:
            items.append(MenuItem(
                acct.username,
                (lambda a_: (lambda app: PasswordScreen(a_, self.registry)))(acct),
                hint=TIERS[acct.tier].label))
        if items:
            items.append(MenuItem("", enabled=False))
        if self.registry.full():
            items.append(MenuItem(labels.LOGIN_AT_CAPACITY, enabled=False))
        else:
            items.append(MenuItem(
                labels.LOGIN_REGISTER,
                lambda app: RegistrationScreen(self.registry)))
        self.menu = Menu(items)

    def _refresh_locks(self) -> None:
        locks = session.read_login_locks()
        now = time.time()
        self._machine_locked_until = locks["machine_end"] \
            if locks["machine_end"] > now else 0.0
        user_locks = locks["users"]
        for item, acct in zip(self.menu.items, self.registry.accounts):
            end = user_locks.get(acct.username, 0.0)
            if self._machine_locked_until:
                item.enabled = False
                item.status = None
            elif end > now:
                item.enabled = False
                item.status = (lambda e: (lambda:
                    f"{labels.LOGIN_LOCKED} {_fmt_remaining(e, time.time())}"))(end)
            else:
                item.enabled = True
                item.status = None

    def draw(self, win, top, left):
        self._refresh_locks()
        if self._machine_locked_until:
            win.addstr(top, left, labels.LOGIN_MACHINE_LOCKED,
                       theme.attr(theme.PAIR_WARN, bold=True))
            win.addstr(top + 1, left,
                       _fmt_remaining(self._machine_locked_until, time.time()),
                       theme.attr(theme.PAIR_WARN))
            return
        self.menu.draw(win, top, left)
        h, w = win.getmaxyx()
        if self.notice:
            win.addstr(top + len(self.menu.items) + 1, left,
                       self.notice[: w - left - 2],
                       theme.attr(theme.PAIR_ACCENT, bold=True))
        else:
            win.addstr(top + len(self.menu.items) + 1, left,
                       f"— {labels.TAGLINE} —"[: w - left - 2],
                       theme.attr(theme.PAIR_DIM, dim=True))

    def status_text(self):
        return labels.LOGIN_HINT

    def handle_key(self, key, app):
        if key in (ord("q"), ord("Q")):
            return power.screen()
        if key in KEYS_BACK:
            return None   # nowhere back to go — this IS the front door
        if self._machine_locked_until:
            return None
        self.notice = ""
        return self.menu.handle_key(key, app)


def build_entry(app):
    """Root-screen factory for __main__: login first, Hub after."""
    return LoginScreen()
