# Architecture

How the pieces fit together on the running machine. Read alongside
[`BUILD-SPEC.md`](BUILD-SPEC.md) (the requirements) and
[`STATUS.md`](STATUS.md) (what's actually built).

## Boot → login → Hub chain

```
GRUB (no quiet/rhgb)                       real kernel messages print
  │
  ▼
Plymouth text theme                        boot log visible, unmodified
  │
  ▼
systemd → multi-user.target                NO display manager, NO graphical.target
  │
  ▼
getty@tty1 autologin  ──────────────►      user "operator" (spec §4)
  │
  ▼
login shell = /usr/local/bin/foundationhub-session
  │   (this is the user's actual shell via chsh; exiting it logs out)
  ▼
`python -m foundationhub` on the kernel VT   ◄──── LOGIN screen, then the Home Hub
      (curses on the text console — no compositor, no graphical
       terminal, no GPU. The session script sets the console font
       and retunes the VT palette to phosphor amber/green first.)
```

Key property from the spec: **the TUI is the login shell.** There is no bash
prompt behind it. `foundationhub-session` execs foundationhub; when foundationhub
exits, the session ends. No shell to drop to.

**No display stack in the core.** The Hub draws on the kernel's own text
console the way DOS programs drew on the BIOS console. A hardware profile
whose glue genuinely needs a display stack installs
`/usr/local/lib/foundationhub/display-stack`, which `foundationhub-session`
execs instead when present — the zenbook-duo-2024 profile does this (cage +
kitty) because its dual-panel topology is driven through `wlr-randr`, which
needs a Wayland compositor. On a generic install that file doesn't exist and
nothing graphical is even installed.

Multi-user (docs/USERS.md): foundationhub now opens on a **login screen** — up to 8
tiered accounts per machine. In the interim layering, the Linux user
`operator` hosts the console session and foundationhub accounts are logical users on
top of it; the Hub publishes the active account to `/run/foundationhub/active-user`
so Frank attributes events per person, and Frank's session-scope locks gate
the login screen via the public `/run/frank/login.locks` summary (usernames +
expiry timestamps only). Real per-account Linux sessions are `TODO(hardware)`.

The session wrapper is a thin script rather than exec'ing the Hub directly so
we can (a) start the per-session sound daemon, (b) set the console font/palette
and export the CRT theme env, (c) hand off to a profile's display-stack plugin
when one is installed, and (d) guarantee that an unexpected foundationhub crash
still logs out rather than exposing a shell.

## Processes on a running system

Generic core (present regardless of hardware profile):

| Unit / process                | Scope      | Runs as | Purpose |
|-------------------------------|------------|---------|---------|
| `getty@tty1` (autologin)      | system     | root→operator | drops into the session |
| `foundationhub-session` → foundationhub | user login | operator | the kiosk surface (kernel VT) |
| `python -m foundationhub`            | user login | operator | Home Hub TUI (the shell) |
| `frankd.service`              | system     | `frank`  | overseer daemon — decides (§6) |
| `frank-enforcer.service`      | system     | **root** | applies lockouts the operator can't bypass (§6) |
| `foundationhub-sound.service`        | user login | operator | ambient hum + event sounds |

Added by the `zenbook-duo-2024` hardware profile only (see
[`PROFILES.md`](PROFILES.md)) — absent on a generic-core install:

| Unit / process                | Scope      | Runs as | Purpose |
|-------------------------------|------------|---------|---------|
| `frank-ledger.service`        | system     | `frank`  | pipes timestamp ledger to eDP-2 on keyboard detach |
| `duo-hardware.service`        | system     | root/polkit | display/rotation/brightness/battery glue |
| cage + kitty (display-stack)  | user login | operator | this profile's Wayland session, needed by its wlr-randr glue |

Frank runs as its **own system user** (`frank`), not as `operator`. This is the
core of the §6 config-protection model: the `operator` account has no read/write
access to Frank's config, logs, or process, and no sudo path to them. See
[Frank isolation](#frank-isolation).

## Frank isolation

Requirement (§6, §11): the logged-in user must not be able to read Frank's
findings, edit its config/thresholds (beyond the narrow Settings sensitivity
knob), see the ledger detail, or kill the process.

Implementation approach:

- Frank runs under a dedicated system user `frank` with its home at
  `/var/lib/frank`.
- Config lives at `/etc/frank/` — `root:frank`, mode `0750` on the dir,
  `0640`/`0600` on files. `operator` cannot read it.
- Findings/detail live at `/var/lib/frank/incidents.db` — `frank:frank`, `0600`.
  Never surfaced through any Hub screen.
- The sorting/sifting and Overseer tiers (see below) keep their own
  frank-only stores under the same isolation model: raw base logs
  at `/var/lib/frank/events.log`, sifted digests at `/var/lib/frank/triage.jsonl`,
  and the Overseer's own decision audit trail at `/var/lib/frank/verdicts.jsonl`
  — all `frank:frank`, `0600`, never surfaced through any interface.
- Lock decisions are published to `/var/lib/frank/lockout.state` —
  `frank:frank`, `0640` (root reads, operator denied).
- **The operator has NO power over Frank — none, ever.** There is no tunable
  knob, no sensitivity setting, no config the operator can edit, no IPC command
  that changes anything. Sensitivity is a *root-only* value in `/etc/frank/`
  loaded once at startup; there is no in-session path to change it. (This
  tightens spec §5's mention of exposed sensitivity tuning, at the user's
  explicit direction.)
- No sudoers/polkit entry grants `operator` anything against `frankd`,
  `frank-enforcer`, `/etc/frank`, or `systemctl … frank*`.
- **Acknowledged limit (spec §6):** this is high-friction in-session tamper
  resistance, *not* immunity to a USB boot disk. Disk encryption / secure boot
  is a deferred later phase. "No power over Frank" is scoped to the running OS.

The Hub ↔ Frank socket (`/run/frank/hub.sock`, group-restricted) is **strictly
read-only for the Hub**: it carries one thing — the Hub asks `poll` and Frank
returns a warning/status line to *display*. The Hub can change nothing about
Frank. See [`frank/frankd/ipc.py`].

### Enforcement is root-owned, not Hub-cooperative

A lockout the operator's own process merely *renders* would be a lockout the
operator has the power to ignore — so lockouts are **not** enforced by the Hub.
`frankd` (user `frank`) *decides* lockouts and publishes the decision to
`lockout.state`. A separate **root** service, `frank-enforcer`, reads it and
applies an unbypassable console lock:

- terminates the operator's active session (`loginctl terminate-user`),
- stops `getty@tty1` so no new session can start until the timer expires,
- shows a root-owned countdown locker (`frank-locker`) that ignores input.

Scope maps to reboot behavior (spec §6): **session** locks end when the session
ends (a reboot clears them); **machine** locks are re-armed by `frankd` on boot
from `lockout.state`, so rebooting cannot escape them. The operator cannot read
the state file, signal the enforcer, or reach a shell — the only escape is
physical/USB, which the spec places out of scope.

## The AI integrations are separate trust domains

Three — same provider(s) available, different clients, different invocation,
different power, never sharing a credential or a code path:

- **Frank commentary** (`frank/frankd/mistral.py`): the approved line bank is
  Frank's **primary, rule-based voice** (operator direction: Frank is a
  primarily rule-based overseer system, OPEN-QUESTIONS.md §5). AI phrasing is
  a double opt-in — the root-only `commentary.ai_enabled` flag AND a key from
  `/etc/frank/secrets.env` (root:frank, 0640; the user's account never sees
  it) — and even then it is **phrasing only — never decides guilt or
  severity** (spec §6), falling back to the bank on any misbehavior.
- **The AI layer** (`frank/frankd/ai.py`, used by `triage.py`/`overseer.py`):
  two narrow roles — the Sifter (a *sensor* whose classifications only become
  findings via the Overseer's deterministic Rulebook thresholds) and the
  Overseer brain (an *opt-in second opinion*, `overseer.ai_enabled`, default
  off) — see below. Own key lines in the same secrets file
  (`FRANK_SIFT_API_KEY` / `FRANK_OVERSEER_API_KEY`), so spend is attributable
  per tier the same way the operator already wanted commentary spend
  attributable.
- **AI Chat** (`hub/foundationhub/aichat.py`): called by the Hub (user `operator`) only
  when the user opens the AI Chat screen and sends a message. Uses a *separate*
  key file the operator can read. This assistant has no access to Frank's data
  or verdict logic.

Keeping them separate keeps costs attributable and prevents the general
assistant from becoming a side channel into Frank.

## Three tiers, one enforcement path

The rule engine was always described as "the primary, always-on mechanism,"
with Mistral commentary explicitly barred from deciding anything (spec §6:
"AI never decides violations"). Two tiers sit *above* it, covering a gap the
rule engine deliberately left open — docs/OPEN-QUESTIONS.md §3 parked a broad
hate-speech/extremism category for periodic review instead of realtime
keyword matching. **Operator direction: Frank is a primarily rule-based
overseer system** (OPEN-QUESTIONS.md §5) — so all three tiers now *decide*
with deterministic rules; AI appears only as a sensor and an opt-in second
opinion, so the whole system runs identically on any machine, online or off.

1. **Rule engine** (`rules.py`) — unchanged. Realtime, offline, every tick.
   Decides what's flagged and how severe, for the categories it has patterns
   for.
2. **Sorting/sifting Frank** (`frank/frankd/triage.py`) — runs on its own
   short interval (`config.TriageConfig`, default 15 min). Reduces recent
   `incidents.db` entries to counts/rule-hit stats (no AI), and runs the raw
   base-log text (`eventlog.py`, shell/browser sources only) through a cheap
   classifier (`ai.py`'s `Sifter`) for the one category that needed periodic
   review instead of keyword matching. The Sifter is a **sensor**: its
   readings carry no authority of their own. This tier **never enforces
   anything and never decides a violation** — it produces a `TriageReport`,
   organized material for the next tier.
3. **The Overseer — "main Frank"** (`frank/frankd/overseer.py`) — the tier
   that renders verdicts. Its brain is the **deterministic `Rulebook`**:
   threshold rules over structured data (root-only values in
   `config.OverseerConfig`), fully offline, every verdict reproducible from
   the logs —
   - *sift accumulation*: confident Sifter readings accumulated across the
     check-in period cross count thresholds → minor/elevated/serious on the
     legal-ethical track (the decision is the threshold, not the model);
   - *slow burn*: many enforced incidents on one track scattered across a
     period, each too far apart to stack the enforcer's 5-minute-decay
     warning score → elevated;
   - *burst*: a SERIOUS finding arriving amid a wide spray of other
     incidents (volume + distinct rules) → serious escalation.

   An **AI second opinion** exists but is OFF by default
   (`overseer.ai_enabled`, root-only, plus a key): it is consulted only when
   the Rulebook flagged nothing and a report still looks noteworthy, and it
   can only *add* a verdict, never veto one.

   Two activation paths (operator-confirmed):
   - **Periodic check-in**, `config.OverseerConfig.checkin_interval_seconds`
     (default twice a day). Reads every `TriageReport` since the last
     check-in plus the raw `incidents.db` window for the whole period (the
     Rulebook counts real entries, not just digests), plus a bounded
     live-activity snapshot.
   - **Immediate wake on a SERIOUS finding** (only SERIOUS — lesser
     lockouts/warnings wait for the next scheduled check-in; operator-
     confirmed scope). Pulls a short lookback window around the trigger.

   Whatever the Overseer decides to flag — Rulebook or second opinion — is
   expressed as an ordinary `Finding` (any track, any severity — this is the
   "intervene on any and all levels" the operator described), routed by
   `UserEnforcers` to the finding's user, and runs through the **exact same**
   `Enforcer.process()` a rule-engine Finding does. There is no second
   enforcement path. That is what makes "the same hard ceiling applies to the
   Overseer" (operator-confirmed) true by construction: the Overseer
   literally cannot reach a different lockout/scope/ceiling calculation than
   the rule engine can, because it's the same function.

See `frank/frankd/ai.py` for the model-choice discussion for the two optional
AI roles — kept as an open, swappable config choice rather than hardcoded,
same as sensitivity was.

## Detection data flow (Frank)

```
data sources (sources.py)                rule engine (rules.py)
  shell history  ─┐                         ┌─ security track  ─┐
  processes      ─┤                         │  (severity tiers) │
  filesystem     ─┼─►  normalized events ─► ┤                   ├─► Finding
  network        ─┤                         │  legal/ethical    │      │
  browser reqs   ─┘                         └─ (severity tiers) ─┘      │
         │ (shell/browser only)                                        │
         ▼                                                              │
   eventlog.py (raw base logs, frank-only)                              │
         │                                                              │
         ▼ periodic, own interval                                      │
   triage.py — TriageEngine                                            │
     stats (no AI) + ai.Sifter on raw text                             │
     for the one parked category ──► TriageReport                      │
         │                                                              │
         ▼ read at its own cadence, OR immediately on a SERIOUS Finding│
   overseer.py — Overseer ("main Frank")                                │
     Rulebook (deterministic thresholds) renders the verdict;           │
     optional AI second opinion (off by default) only if rules          │
     found nothing; flagged => synthetic Finding ───────────────────────┤
                                                                         ▼
                            flagged/ambiguous only            enforcement.py
                                              mistral.py       (warn → lockout
                                              (commentary       state machine;
                                              only — phrases    hard cooldown
                                              it, never          ceiling)
                                              decides guilt)          │
                          ┌─────────────────────────┼───────────────────────┐
                          ▼                         ▼                        ▼
                   ledger.py (timestamps      IPC → Hub (warn/          incidents.db
                   only, to eDP-2 on          lockout banners)          (full detail,
                   keyboard detach)                                     frank-only)
```

Design invariants baked into the code, straight from §6 (the last one scoped
by this session — see "Three tiers, one enforcement path" above):

- **Severity → lockout duration.** **Time-of-day → context/ledger reset.** These
  two axes never cross. See `enforcement.py` and `ledger.py`.
- **Hard cooldown is an absolute ceiling.** Frank can lengthen a lockout up to
  the ceiling for severe events but can never exceed or bypass it. It always
  eventually expires — including for a lockout the Overseer triggers; it goes
  through the identical `Enforcer.process()`.
- **Ledger shows timestamps only.** The visible ledger is machine-formatted
  timestamps — no category, severity, description, or content. Detail is
  frank-only.
- **Rules decide; AI is a sensor or a second opinion, never the authority.**
  Mistral commentary (`mistral.py`) only writes the words for a verdict the
  rule layer already reached — and the rule-based line bank is the primary
  voice even for that. The Sifter's classifications become Findings only when
  the Overseer Rulebook's deterministic thresholds say so, and the Overseer's
  AI brain is an opt-in (default-off) second opinion consulted only when the
  Rulebook found nothing — additive, never a veto. Everything that CAN
  produce a Finding is bounded by the same `Enforcer.process()`.

## The Home Hub (foundationhub)

A pure-stdlib `curses` app so it has zero install-time dependencies and can be
smoke-tested off-device. Structure:

- `app.py` — screen stack + main loop + input dispatch (arrows/hjkl, Enter,
  Esc/Backspace).
- `theme.py` — CRT palettes (amber primary, green alt), color-pair setup,
  scanline/glow chrome.
- `ui.py` — reusable widgets: the highlight-and-Enter `Menu`, framed panels,
  status bar, full-screen banner.
- `labels.py` — **every** user-visible label in one place, so the wording
  review (spec §5, §10) is a single-file diff.
- `screens/` — one module per Home Hub area (Programs, Recreation, Functions
  Control, Settings, Log, Personal Notes, AI Chat).
- `session.py` — the Frank IPC client (receives warn/lockout, renders banners
  and the lock screen) and the launch helpers used by the hybrid model below.

**Hybrid model (decided, `OPEN-QUESTIONS.md` §10):** not everything the user
"does" is a `launch()` anymore. Core apps — notes, file manager, system
monitor — are native Hub screens (`screens/notes.py`, `screens/files.py`,
`screens/monitor.py`) with their own testable backends (`notesdb.py`,
`fileops.py`, `sysinfo.py`); the Hub draws them directly. Heavier apps — the
media player and the games — are separate in-house programs the Hub still
reaches with `launch()`, now pointed at our own binaries
(`foundation-arcade`, `foundation-chess`, `foundationmedia`) plus, per the
operator's download-don't-build call on Rogue specifically (feedback #2,
`docs/FEEDBACK-FIRST-HARDWARE-RUN.md`), the 1981 Berkeley original built from
vendored source at ISO build time (`rogue` — see `vendor/rogue3.6`) instead of
a borrowed one. `ranger`, `btop`, and `nvim` are retired; `nethack` was removed
entirely (operator direction 2026-07-05); `crawl` was never actually listed
there. The "nicer" graphical 1985 Rogue is a **downloadable** slot, not shipped
— no redistributable upstream (operator direction 2026-07-06;
`docs/ROGUE-DOWNLOADABLE.md`). The in-house "Foundation Depths" modernized
roguelike (`docs/ROGUELIKE-DESIGN.md`) remains a possible future project,
separate from the classic Rogue above. The Hub is glue + chrome + the
Frank-facing surfaces; it does not reimplement the in-house programs — those
live in their own top-level `games/`/`media/` packages and import
`foundationhub.theme`/`ui` for chrome rather than the other way around.

## Hardware glue is a profile, not core

None of the above (boot chain, Hub, Frank) depends on any specific device.
Device-specific glue lives entirely under `profiles/<name>/` and is only
applied when `HARDWARE_PROFILE` is set (see [`PROFILES.md`](PROFILES.md)).
The Hub calls into hardware helpers only through `hub/foundationhub/session.py`'s
`HW_BIN` indirection, which degrades gracefully to "not available" when no
profile — or a different one — is installed; nothing in the core branches on
device identity.

The one shipped profile, `zenbook-duo-2024`, is ported from
`alesya-h/zenbook-duo-2024-ux8406ma-linux` with GNOME parts replaced:

- `display-stack` — the profile's own cage+kitty Wayland session (the core
  runs on the plain VT and needs none); required because everything below
  drives displays through `wlr-randr`.
- `duo-watch-displays` — was GNOME session watcher; now drives `wlr-randr`
  against cage.
- `duo-screen-toggle` — was `gnome-monitor-config`; now `wlr-randr`.
- `duo-keyboard-detach` — udev-driven; emits a single event consumed by
  **both** display topology and Frank's ledger service (`frank-ledger.service`,
  itself part of this profile — see below).
- `backlight-sync` — syncs eDP-1/eDP-2 brightness via
  `backlight=card1-eDP-2-backlight`; privilege via scoped **polkit** rule, not
  the original blanket `NOPASSWD /usr/bin/env` hole.
- Battery limiter, rotation (iio-sensor-proxy), libwacom digitizer files port
  directly (GNOME-agnostic).

See `profiles/zenbook-duo-2024/README.md` for the full file-by-file mapping.
