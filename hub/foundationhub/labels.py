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
LOGIN_CREATE_SLOT = "[ CREATE NEW USER ]"   # placeholder row for an unused slot
LOGIN_PASSWORD_FOR = "AUTHENTICATION — {user}"
LOGIN_PASSWORD_PROMPT = "PASSWORD"
LOGIN_DENIED = "ACCESS DENIED"
LOGIN_COOLDOWN = "TOO MANY FAILURES — WAIT"
LOGIN_LOCKED = "LOCKED"
LOGIN_MACHINE_LOCKED = "TERMINAL LOCKED BY THE OVERSEER"
LOGIN_VIOLATIONS = "VIOLATIONS"     # per-account count from Frank's public summary
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

# ── Top-level Home Hub (feedback #8 — reworked IA) ───────────────────────────
HUB_TITLE = "TERMINAL // MAIN"
HUB_SUBTITLE = f"{BRAND} — AUTHORIZED USE ONLY"

# Order shown on the Home Hub:  PROGRAMS · RECREATION · SETTINGS · LOGS · POWER
PROGRAMS = "PROGRAMS"
RECREATION = "RECREATION"
HIGH_SCORES = "HIGH SCORES"     # one system-wide board per game (never per user)
HIGH_SCORES_EMPTY = "(no scores recorded yet)"
HIGH_SCORES_CHESS = "CHESS"                       # machine-wide W/L/D, not a beatable score
HIGH_SCORES_CHESS_FMT = "W {w} · L {l} · D {d}"
SETTINGS = "SETTINGS"           # was FUNCTIONS — toggles + network + the status readout
STATUS = "SYSTEM STATUS"        # now a read-only readout reached from inside SETTINGS
LOGS = "LOGS"
POWER = "POWER"

# Assistant (AI Chat) — an on-demand, on-device general assistant (spec §5).
# It talks to the SAME local model server Frank uses, but is a separate trust
# domain with no access to Frank's data/verdicts (see aiclient.py). Back on the
# Hub menu (2026-07-09) now that it actually talks to the local model.
ASSISTANT = "ASSISTANT"
ASSISTANT_SUBTITLE = "on-device AI — local model, separate from the overseer"
ASSISTANT_INTRO = "On-device assistant. Type a message and press Enter."
ASSISTANT_PROMPT = "You"
# Shown while the model is generating — keeps the screen from looking frozen
# during the (bounded) HTTP wait.
ASSISTANT_THINKING = "… thinking"
# Offline / failure notices. Short enough for a 80-col CRT line; detail lives
# in docs/FRANK-LOCAL-AI.md and INSTALL.md §2.
ASSISTANT_OFFLINE = (
    "Local model not reachable (frank-ai.service on 127.0.0.1:8080). "
    "Stage llama-server + model.gguf (docs/FRANK-LOCAL-AI.md), then start the service.")
ASSISTANT_ERROR_HTTP = (
    "Model server answered with an error. Check frank-ai.service / model name.")
ASSISTANT_ERROR_EMPTY = "Model returned an empty reply. Try again."
ASSISTANT_ERROR_BAD = "Model reply was unreadable. Try again."
ASSISTANT_HINT = "type   ↵ send   Esc back"

# ── Programs (order: Notes · Notes Search · Files · Media · Monitor) ──────────
NOTES = "NOTES"                 # the single notes home (feedback #8)
NOTES_SEARCH = "NOTES SEARCH"   # separate search program — Work-only by default
PROG_FILES = "FILE MANAGER"
PROG_MEDIA = "MEDIA"
PROG_MONITOR = "SYSTEM MONITOR"

# ── Functions Control (real toggles only — spec §5) ──────────────────────────
FN_BRIGHTNESS = "DISPLAY BRIGHTNESS"
FN_SECOND_SCREEN = "SECOND PANEL"
FN_POWER_PROFILE = "POWER PROFILE"
FN_SOUND = "SOUND"
FN_TEXT_SIZE = "TEXT SIZE"

# ── System Update (docs/UPDATE-SYSTEM.md — on-demand only, no daemon) ─────────
UPDATE = "SYSTEM UPDATE"
UPDATE_SUBTITLE = "updates run only when asked — nothing checks by itself"
UPDATE_CHECK = "CHECK FOR UPDATES"
UPDATE_APPLY = "APPLY UPDATE"
UPDATE_POLICY = "UPDATE POLICY"
UPDATE_VERSION_HEADING = "VERSION"
UPDATE_USB_HINT = "USB updates: boot the release stick — it offers UPDATE"
UPDATE_UP_TO_DATE = "UP TO DATE"
UPDATE_AVAILABLE = "UPDATE AVAILABLE"
UPDATE_APPLYING = "APPLYING — DO NOT POWER OFF"
UPDATE_TECH_ONLY = "TECHNICIAN CLEARANCE REQUIRED"
UPDATE_CODE_PROMPT = "TECHNICIAN SETUP CODE?"
UPDATE_DONE = "UPDATED — RESTART TO FINISH (POWER MENU)"

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

# ── Notes — one home in Programs: a tabbed, command-driven note list ──────────
# A single screen with a WORK | PERSONAL tab switch, one numbered "available
# notes" list (each row shows when it was last edited), and a one-line command
# area. Everything is a plain .md file; Work and Personal are two folders on
# disk. Each section also has its own one-page-per-day Journal, reached with `j`.
NOTES_SUBTITLE = "WORK | PERSONAL — a numbered list you drive by command"
NOTES_WORK = "WORK"
NOTES_PERSONAL = "PERSONAL"
NOTES_AVAILABLE = "AVAILABLE NOTES"
NOTES_TAB_HINT = "Tab / ←→ switch   ↑↓ scroll"
NOTES_NAME_PROMPT = "NEW NOTE NAME:"
NOTES_EMPTY = "(no notes yet — press  n  to create one)"
NOTES_CMD_PROMPT = "command:"
NOTES_HINT = "#=open   n=new note   j=journal   x #=delete   q/Esc=quit"
NOTES_UNKNOWN = "UNKNOWN — # open · n new · j journal · x# delete · q quit"
NOTES_NO_SUCH = "NO NOTE NUMBERED {n}"
NOTES_DELETE_NONE = "NO VALID NOTE NUMBERS TO DELETE"
NOTES_DELETE_CONFIRM = "DELETE {n} NOTE(S)?   y / N"
NOTES_DELETED = "DELETED {n} NOTE(S)"

# Journal — one page per day, kept per section (a Work journal and a Personal
# journal). `j` opens today's page, creating it on first save.
NOTE_JOURNAL = "JOURNAL"
NOTE_JOURNAL_TAG = "·journal"

# Notes Search (separate program) — Work-only by default, opt into Personal.
NOTES_SEARCH_SUBTITLE = "words match text, #tags match tags"
NOTES_SEARCH_ASK = "INCLUDE PERSONAL NOTES?   y / N   (default: no)"
SEARCH_PROMPT = "QUERY (words and #tags)"
SEARCH_NONE = "NO MATCHING RECORDS"
SEARCH_HINT = "type   ↵ search   Esc back"
SEARCH_RESULTS_HINT = "↑↓/jk move   ↵ open   Esc new search"

# ── File Manager (native Hub screen — queue §2) ──────────────────────────────
FILES_UP = ".. (up)"
FILES_EMPTY = "(empty)"
FILES_NAME_PROMPT = "NAME"
FILES_RENAME_PROMPT = "NEW NAME"
FILES_EXISTS = "A FILE BY THAT NAME EXISTS"
FILES_INVALID_NAME = "INVALID NAME"
FILES_DELETE_CONFIRM = "DELETE {name}?  y/n"
FILES_DELETED = "DELETED"
FILES_MARKED_COPY = "MARKED TO COPY: {name}"
FILES_MARKED_CUT = "MARKED TO CUT: {name}"
FILES_NOTHING_MARKED = "NOTHING MARKED"
FILES_PASTED = "PASTED"
FILES_CANNOT_OPEN = "CANNOT OPEN (not a text file)"
FILES_HINT = ("↵ open   n new dir   r rename   d delete   "
              "c copy   x cut   v paste   Esc/⌫ back/up")

# ── System Monitor (native Hub screen, view-only — queue §3) ─────────────────
MONITOR_TITLE = "SYSTEM MONITOR"
MONITOR_SUBTITLE = "view-only — kill/renice is root/overseer territory"
MONITOR_NO_PROC = "HOST DOES NOT EXPOSE /proc"
MONITOR_NO_PROC_DETAIL = "display only on target hardware"
MONITOR_CPU = "CPU"
MONITOR_MEM = "MEMORY"
MONITOR_UPTIME = "UPTIME"
MONITOR_LOAD = "LOAD"
MONITOR_NET = "NETWORK"
MONITOR_PROCESSES = "PROCESSES"
MONITOR_PROC_HEADER = f"{'PID':>7}  {'NAME':<20}{'CPU%':>7}{'MEM':>10}"
MONITOR_HINT = "auto-refresh   Esc/⌫ back"

# ── The system text editor (one-editor policy — queue §1) ────────────────────
EDITOR_TITLE = "TEXT EDITOR"
EDITOR_SUBTITLE = "ALL ENTRIES ARE PART OF THE PERMANENT RECORD"
EDITOR_MENU_SAVE = "SAVE"
EDITOR_MENU_RENAME = "RENAME"
EDITOR_MENU_DISCARD = "DISCARD"
EDITOR_MENU_RETURN = "RETURN"
EDITOR_HINT = "type   Esc menu"
EDITOR_MODIFIED = "modified"
EDITOR_SAVE_FAILED = "SAVE FAILED: {err}"
EDITOR_RENAME_PROMPT = "RENAME TO"
EDITOR_RENAME_EXISTS = "A RECORD BY THAT NAME EXISTS"

# ── Frank negotiation (docs/FRANK-LOCAL-AI.md §4) ─────────────────────────
NEGOTIATE_TITLE = "REVIEW"
NEGOTIATE_SUBTITLE = "this restriction is open to negotiation"
NEGOTIATE_INTRO = ("You are being frank with me. I am being frank with you. "
                   "State your case. I decide.")
NEGOTIATE_PROMPT = "Your statement"
NEGOTIATE_DONE = "Esc to return · any key to speak again"
NEGOTIATE_OFFLINE = "The overseer is not reachable."

# ── Power ────────────────────────────────────────────────────────────────────
POWER_LOGOUT = "LOG OUT"
POWER_REBOOT = "REBOOT"
POWER_SHUTDOWN = "SHUT DOWN"

# ── Common chrome / footer hints ─────────────────────────────────────────────
HINT_NAV = "↑↓/jk move   ↵ select   Esc/⌫ back"
HINT_TOP = "↑↓/jk move   ↵ select   q power"
NOT_INSTALLED = "[ not installed — see docs/OPEN-QUESTIONS.md ]"
