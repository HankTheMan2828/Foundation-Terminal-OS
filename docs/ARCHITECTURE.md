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
login shell = /usr/local/bin/zenhub-session
  │   (this is the user's actual shell via chsh; exiting it logs out)
  ▼
cage (Wayland kiosk compositor)
  └── launches ONE fullscreen kitty
        └── runs `python -m zenhub`  ◄──── the Home Hub TUI
```

Key property from the spec: **the TUI is the login shell.** There is no bash
prompt behind it. `zenhub-session` execs cage→kitty→zenhub; when zenhub exits,
the whole chain unwinds and the session ends. No shell to drop to.

The session wrapper is a thin script rather than making cage itself the shell so
we can (a) start the per-session sound daemon, (b) export the CRT theme env, and
(c) guarantee that an unexpected zenhub crash still logs out rather than
exposing a shell.

## Processes on a running system

| Unit / process                | Scope      | Runs as | Purpose |
|-------------------------------|------------|---------|---------|
| `getty@tty1` (autologin)      | system     | root→operator | drops into the session |
| `zenhub-session` → cage→kitty | user login | operator | the kiosk surface |
| `python -m zenhub`            | user login | operator | Home Hub TUI (the shell) |
| `frankd.service`              | system     | `frank`  | overseer daemon (§6) |
| `frank-ledger.service`        | system     | `frank`  | pipes timestamp ledger to eDP-2 on keyboard detach |
| `duo-hardware.service`        | system     | root/polkit | display/rotation/brightness/battery glue |
| `zenhub-sound.service`        | user login | operator | ambient hum + event sounds |

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
- The **only** user-tunable knob is a sensitivity value, exposed through a
  narrow, validated IPC: the Hub writes a single integer to a request, `frankd`
  validates and applies it. The Hub never edits Frank's files directly. See
  [`frank/frankd/ipc.py`].
- No sudoers entry grants `operator` anything against `frankd`, `/etc/frank`, or
  `systemctl … frankd`.
- **Acknowledged limit (spec §6):** this is high-friction in-session tamper
  resistance, *not* immunity to a USB boot disk. Disk encryption / secure boot
  is a deferred later phase. We do not over-engineer it in v1.

The Hub ↔ Frank boundary is a small unix-socket IPC (`/run/frank/hub.sock`,
group-restricted) carrying exactly three message types: `warn` (Frank→Hub, show
a status-bar or full-screen banner), `lockout` (Frank→Hub, enter/refresh a
lock screen with a countdown), and `set_sensitivity` (Hub→Frank, the one
allowed knob). Nothing else crosses.

## The two Mistral integrations are separate

Same provider, different clients, different invocation, different trust domain:

- **Frank commentary** (`frank/frankd/mistral.py`): called by `frankd` (user
  `frank`) *only* when the rule layer flags an ambiguous/serious event. Uses the
  key from `/etc/frank/secrets.env` (root:frank, 0640). The user's account never
  sees this key.
- **AI Chat** (`hub/zenhub/aichat.py`): called by the Hub (user `operator`) only
  when the user opens the AI Chat screen and sends a message. Uses a *separate*
  key file the operator can read. This assistant has no access to Frank's data
  or verdict logic.

Keeping them separate keeps costs attributable and prevents the general
assistant from becoming a side channel into Frank.

## Detection data flow (Frank)

```
data sources (sources.py)                rule engine (rules.py)
  shell history  ─┐                         ┌─ security track  ─┐
  processes      ─┤                         │  (severity tiers) │
  filesystem     ─┼─►  normalized events ─► ┤                   ├─► verdict
  network        ─┤                         │  legal/ethical    │
  browser reqs   ─┘                         └─ (severity tiers) ─┘
                                                    │
                            flagged/ambiguous only  ▼
                                              mistral.py  (commentary only —
                                              phrases it, never decides guilt)
                                                    │
                                                    ▼
                                   enforcement.py  (warn → lockout state
                                   machine; hard cooldown ceiling)
                                                    │
                          ┌─────────────────────────┼───────────────────────┐
                          ▼                         ▼                        ▼
                   ledger.py (timestamps      IPC → Hub (warn/          incidents.db
                   only, to eDP-2 on          lockout banners)          (full detail,
                   keyboard detach)                                     frank-only)
```

Design invariants baked into the code, straight from §6:

- **Severity → lockout duration.** **Time-of-day → context/ledger reset.** These
  two axes never cross. See `enforcement.py` and `ledger.py`.
- **Hard cooldown is an absolute ceiling.** Frank can lengthen a lockout up to
  the ceiling for severe events but can never exceed or bypass it. It always
  eventually expires.
- **Ledger shows timestamps only.** The visible ledger is machine-formatted
  timestamps — no category, severity, description, or content. Detail is
  frank-only.
- **AI never decides violations.** The rule layer decides *what* is flagged and
  *how severe*; Mistral only writes the words.

## The Home Hub (zenhub)

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
  and the lock screen) and the launch helpers that shell out to ranger/btop/
  games/etc. with graceful "not installed" handling.

Everything the user "does" that isn't navigation is a `launch()` into a real
program (ranger, btop, nethack, …). The Hub is glue + chrome + the Frank-facing
surfaces; it does not reimplement those tools.

## Hardware glue (Zenbook Duo)

Ported from `alesya-h/zenbook-duo-2024-ux8406ma-linux`, GNOME parts replaced:

- `hardware/duo-watch-displays` — was GNOME session watcher; now drives
  `wlr-randr` against cage.
- `hardware/duo-screen-toggle` — was `gnome-monitor-config`; now `wlr-randr`.
- `hardware/duo-keyboard-detach` — udev-driven; emits a single event consumed by
  **both** display topology and Frank's ledger service.
- `hardware/backlight-sync` — syncs eDP-1/eDP-2 brightness via
  `backlight=card1-eDP-2-backlight`; privilege via scoped **polkit** rule, not
  the original blanket `NOPASSWD /usr/bin/env` hole.
- Battery limiter, rotation (iio-sensor-proxy), libwacom digitizer files port
  directly (GNOME-agnostic).
