"""Every user-visible label in one place.

Spec §5 and §10: all menu wording is placeholder pending the operator's review.
Centralizing it here makes the wording review a single-file diff — approving or
rewriting labels never touches screen logic. See docs/OPEN-QUESTIONS.md §1.

Flavor register: Vault-Tec / Aperture Science meets plain practicality.
Nothing here is final. [TODO(approval)]
"""

# ── Top-level Home Hub ────────────────────────────────────────────────────────
HUB_TITLE = "TERMINAL // MAIN"
HUB_SUBTITLE = "OPERATOR CONSOLE — AUTHORIZED USE ONLY"

# Order here is the order shown on the Home Hub.
PROGRAMS = "PROGRAMS"
RECREATION = "RECREATION"
FUNCTIONS = "FUNCTIONS"
SETTINGS = "CONFIGURATION"
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

# ── Settings / Configuration ─────────────────────────────────────────────────
SET_RESOURCE = "RESOURCE LIMITS"
SET_NETWORK = "NETWORK"
SET_AUTH = "USER / AUTH"
SET_THEME = "THEME & SOUND"
SET_OVERSEER = "OVERSEER SENSITIVITY"   # the ONE Frank knob (spec §5)

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
