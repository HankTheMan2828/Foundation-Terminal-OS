"""Account registry + tier model (docs/USERS.md).

Terminals are shared company machines: up to MAX_ACCOUNTS accounts per
machine, each with a fixed storage allotment set by its employee tier.
Anything above GUEST can only be provisioned by a technician presenting the
setup code (a placeholder until the company user-ID system exists — the
Account.user_id field is reserved for it).

Passwords and the setup code are salted PBKDF2-SHA256 — pure stdlib, same
portability constraint as the rest of the Hub. The registry itself is one
JSON file: /etc/foundationhub/users.json on the target (root-owned; mutations go
through the root helper `foundationhub-account`), or $FOUNDATIONHUB_USERS for development,
where the Hub writes it directly.
"""
from __future__ import annotations

import enum
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_ACCOUNTS = 8          # per machine, full stop (docs/USERS.md)
DEFAULT_SETUP_CODE = "1234"   # placeholder until the user-ID system [TODO(approval)]

_PBKDF2_ITERATIONS = 200_000
_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,15}$")

GiB = 1024 ** 3
MiB = 1024 ** 2


class Tier(enum.IntEnum):
    """Employee levels. Higher tier = larger fixed storage allotment."""
    GUEST = 0
    EMPLOYEE = 1
    SENIOR = 2
    TECHNICIAN = 3


@dataclass(frozen=True)
class TierInfo:
    label: str
    quota_bytes: int
    needs_setup_code: bool


# Tier names + quota amounts operator-approved 2026-07-02 (docs/USERS.md);
# the model is fixed per-tier allotments, guests get almost nothing.
TIERS: dict[Tier, TierInfo] = {
    Tier.GUEST:      TierInfo("GUEST",      64 * MiB,  False),
    Tier.EMPLOYEE:   TierInfo("EMPLOYEE",    5 * GiB,  True),
    Tier.SENIOR:     TierInfo("SENIOR",     15 * GiB,  True),
    Tier.TECHNICIAN: TierInfo("TECHNICIAN", 25 * GiB,  True),
}


class RegistryError(Exception):
    """Registration/lookup failure with an operator-facing message."""


# ── password hashing (stdlib only) ───────────────────────────────────────────

def hash_secret(secret: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(),
                                 _PBKDF2_ITERATIONS)
    return f"pbkdf2-sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_secret(secret: str, stored: str) -> bool:
    try:
        algo, iters, salt, hexdigest = stored.split("$")
        if algo != "pbkdf2-sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(),
                                     int(iters))
        return hmac.compare_digest(digest.hex(), hexdigest)
    except (ValueError, AttributeError):
        return False


# ── the registry ─────────────────────────────────────────────────────────────

@dataclass
class Account:
    username: str
    tier: Tier
    pwhash: str
    created: float = field(default_factory=time.time)
    user_id: str = ""       # reserved: company user-ID system (docs/USERS.md)

    @property
    def info(self) -> TierInfo:
        return TIERS[self.tier]


def registry_path() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_USERS", "/etc/foundationhub/users.json"))


class Registry:
    """The machine's account list. Load-once, explicit save."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else registry_path()
        self.accounts: list[Account] = []
        self._setup_code_hash = ""
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        self._setup_code_hash = data.get("setup_code_hash", "")
        self.accounts = []
        for entry in data.get("accounts", [])[:MAX_ACCOUNTS]:
            try:
                self.accounts.append(Account(
                    username=entry["username"],
                    tier=Tier(int(entry["tier"])),
                    pwhash=entry["pwhash"],
                    created=float(entry.get("created", 0)),
                    user_id=entry.get("user_id", ""),
                ))
            except (KeyError, ValueError):
                continue   # one corrupt entry must not take down login

    def save(self) -> None:
        """Atomic write. Raises RegistryError where the caller should fall
        back to the root helper (registry unwritable = not the dev path)."""
        if not self._setup_code_hash:
            self._setup_code_hash = hash_secret(DEFAULT_SETUP_CODE)
        data = {
            "version": 1,
            "setup_code_hash": self._setup_code_hash,
            "accounts": [{
                "username": a.username,
                "tier": int(a.tier),
                "pwhash": a.pwhash,
                "created": a.created,
                "user_id": a.user_id,
            } for a in self.accounts],
        }
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, indent=1))
            os.replace(tmp, self.path)
        except OSError as exc:
            raise RegistryError(f"registry not writable ({exc})") from exc
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ── queries ──────────────────────────────────────────────────────────────
    def get(self, username: str) -> Account | None:
        for a in self.accounts:
            if a.username == username:
                return a
        return None

    def full(self) -> bool:
        return len(self.accounts) >= MAX_ACCOUNTS

    def verify_login(self, username: str, password: str) -> Account | None:
        acct = self.get(username)
        if acct and verify_secret(password, acct.pwhash):
            return acct
        return None

    def verify_setup_code(self, code: str) -> bool:
        stored = self._setup_code_hash or hash_secret(DEFAULT_SETUP_CODE)
        return verify_secret(code, stored)

    # ── mutation (dev path; on the target this happens in foundationhub-account) ────
    def add_account(self, username: str, password: str, tier: Tier,
                    setup_code: str | None = None) -> Account:
        if self.full():
            raise RegistryError(f"terminal at capacity ({MAX_ACCOUNTS} accounts)")
        if not _USERNAME_RE.match(username):
            raise RegistryError("username: a-z 0-9 _ - only, starts with a letter, max 16")
        if self.get(username):
            raise RegistryError("that designation is already registered")
        if TIERS[tier].needs_setup_code:
            if not self.verify_setup_code(setup_code or ""):
                raise RegistryError("setup code rejected — technician required")
        if tier is not Tier.GUEST and not password:
            raise RegistryError("a password is required above GUEST tier")
        acct = Account(username=username, tier=tier,
                       pwhash=hash_secret(password))
        self.accounts.append(acct)
        try:
            self.save()
        except RegistryError:
            self.accounts.pop()
            raise
        return acct
