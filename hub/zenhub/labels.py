"""Every user-visible label in one place.

Centralizing wording here makes any wording change a single-file diff —
rewriting labels never touches screen logic.

Flavor register: Vault-Tec / Aperture Science meets plain practicality.
✅ APPROVED — the operator locked this label set (docs/OPEN-QUESTIONS.md §1);
the alternate drafts were dropped. Future edits are ordinary changes, not
pending decisions.
"""

# ── Official branding (operator-decided 2026-07-01) ──────────────────────────
BRAND = "FOUNDATION TERMINALOS"
TAGLINE = "FROM THE FOUNDATION"

# ── Login (the terminal's front door — docs/USERS.md) ────────────────────────
LOGIN_TITLE = "TERMINAL // ACCESS"
LOGIN_SUBTITLE = f"{BRAND} — ALL ACCESS IS RECORDED"
LOGIN_REGISTER = "NEW OPERATOR REGISTRATION"
LOGIN_PASSWORD_FOR = "AUTHENTICATION — {user}"
LOGIN_PASSWORD_PROMPT = "PASSWORD"
LOGIN_DENIED = "ACCESS DENIED"
LOGIN_COOLDOWN = "TOO MANY FAILURES — WAIT"
LOGIN_LOCKED = "LOCKED"
LOGIN_MACHINE_LOCKED = "TERMINAL LOCKED BY THE OVERSEER"
LOGIN_AT_CAPACITY = "TERMINAL AT ACCOUNT CAPACITY (8)"
LOGIN_HINT = "↑↓/jk move   ↵ select   q power"

REG_TITLE = "OPERATOR REGISTRATION"
REG_USERNAME = "DESIGNATION"
REG_TIER = "CLEARANCE TIER"
REG_SETUP_CODE = "TECHNICIAN SETUP CODE"
REG_PASSWORD = "PASSWORD"
REG_PASSWORD_CONFIRM = "CONFIRM PASSWORD"
REG_MISMATCH = "PASSWORDS DO NOT MATCH"
REG_DONE = "ACCOUNT REGISTERED — WELCOME ABOARD"
REG_HINT = "type   ↵ confirm   Esc cancel"

# ── Top-level Home Hub ────────────────────────────────────────────────────────
HUB_TITLE = "TERMINAL // MAIN"
HUB_SUBTITLE = f"{BRAND} — AUTHORIZED USE ONLY"

# Order here is the order shown on the Home Hub.
PROGRAMS = "PROGRAMS"
RECREATION = "RECREATION"
FUNCTIONS = "FUNCTIONS"
STATUS = "SYSTEM STATUS"
LOGS = "LOGS"
NOTES = "PERSONAL FILE"
ASSISTANT = "ASSISTANT"
POWER = "POWER"

# ── Programs ─────────────────────────────────────────────────────────────────
PROG_FILES = "FILE MANAGER"
PROG_MEDIA = "MEDIA"
PROG_MONITOR = "SYSTEM MONITOR"
PROG_EDITOR = "TEXT EDITOR"

# ── Functions Control (real toggles only — spec §5) ──────────────────────────
FN_BRIGHTNESS = "DISPLAY BRIGHTNESS"
FN_SECOND_SCREEN = "SECOND PANEL"
FN_POWER_PROFILE = "POWER PROFILE"
FN_THEME = "THEME & SOUND"

# ── System Status (network config + read-only identity/health, no admin
# knobs — resource limits and user/auth actions were dropped at the user's
# explicit direction; see docs/OPEN-QUESTIONS.md §1) ─────────────────────────
STATUS_NETWORK = "NETWORK"
STATUS_USER_HEADING = "USER"
STATUS_FUNCTIONS_HEADING = "FUNCTIONS"
STATUS_CHECK_NETWORK = "NETWORK"
STATUS_CHECK_AUDIO = "AUDIO"
STATUS_CHECK_FRANK = "OVERSEER (FRANK)"
STATUS_FUNCTIONING = "FUNCTIONING"
STATUS_NOT_FUNCTIONING = "NOT FUNCTIONING"
# NOTE: there is intentionally no overseer/Frank setting. The operator has no
# power over Frank, ever — nothing to expose here.

# ── Logs (two distinct sections — spec §5) ───────────────────────────────────
LOG_SYSTEM = "SYSTEM RECORDS"           # journald/kernel/auth, raw
LOG_OVERSEER = "OVERSEER LEDGER"        # Frank's ledger — timestamps only (§6)

# ── Personal File (journal + tagged notes — spec §5) ─────────────────────────
NOTE_JOURNAL = "DATED JOURNAL"
NOTE_TAGGED = "TAGGED NOTES"

# ── Power ────────────────────────────────────────────────────────────────────
POWER_LOGOUT = "LOG OUT"
POWER_REBOOT = "REBOOT"
POWER_SHUTDOWN = "SHUT DOWN"

# ── Common chrome / footer hints ─────────────────────────────────────────────
HINT_NAV = "↑↓/jk move   ↵ select   Esc/⌫ back"
HINT_TOP = "↑↓/jk move   ↵ select   q power"
NOT_INSTALLED = "[ not installed — see docs/OPEN-QUESTIONS.md ]"
NO_API_KEY = "[ NO API KEY CONFIGURED — offline ]"
STUB_NOTICE = "[ stub — behavior lands in a later pass ]"
