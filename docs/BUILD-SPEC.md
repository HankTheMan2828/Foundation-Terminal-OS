# Zenbook Duo Terminal OS — Build Specification

> This is the authoritative specification as provided. It is preserved verbatim
> as the source of truth. Implementation notes and decisions derived from it
> live in the other files in `docs/`.

## Vision

A fully console-based Arch Linux system for a 2024 Asus Zenbook Duo
(UX8406MA). No desktop environment, no window manager chrome, no typed shell
commands in normal use. The entire system is navigated like a Fallout 4
terminal or an Aperture Science console: highlight an option, press Enter.
Boot shows the real kernel/systemd log. Login drops straight into a custom
menu system that functions as the login shell itself — there is no bash prompt
to fall back to. An always-on monitoring/accountability layer ("Frank")
watches real system usage and can restrict access to the machine based on
rule-based detection plus AI-generated commentary, with a cold
corporate-menacing personality.

## 1. Base System

- **Distro:** Arch Linux (chosen over Fedora specifically because this build
  is being done from scratch/ground-up rather than adapting an existing
  install)
- **Kernel:** `linux-lts`, pinned. Rationale: the Zenbook Duo's second
  (bottom) display has a known i915 regression on kernel 6.9+ (last
  confirmed-good mainline version was 6.8.12). LTS avoids chasing this churn.
  If `linux-lts`'s current version still exhibits the bug, fall back to pinning
  a known-good version via the Arch Linux Archive.
- **Hardware:** Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor Lake, dual eDP
  panels (eDP-1 top/primary, eDP-2 bottom/secondary), detachable Bluetooth
  keyboard.

## 2. Display Architecture

- No display manager, no desktop environment.
- systemd boots to `multi-user.target` (no `graphical.target`).
- A Wayland kiosk compositor — **cage** — launches a single fullscreen
  **kitty** (or foot) terminal instance on login. No window chrome, no window
  switching, no multitasking surface beyond what's built into the nav system
  itself.
- Multi-monitor handling (enabling/disabling/positioning the second panel) via
  **wlr-randr**, replacing the original community project's
  `gnome-monitor-config` dependency.
- Visual theme: amber/green CRT phosphor look, scanlines, glow. Monospace
  bitmap-style font (e.g. Terminus or similar).

## 3. Boot Sequence

- Plymouth set to a text-based theme (not a themed splash) — real
  kernel/systemd boot messages are visible, unmodified. No fictional flavor
  text layered into the boot log itself.
- `quiet` and `rhgb` kernel params removed from GRUB so messages actually
  print.

## 4. Login & Navigation Model

- No typed commands anywhere in normal operation. All navigation is highlight +
  Enter (arrow keys or vim-style keys, Esc/Backspace to go back).
- The user's login shell is not bash — it's set (via `chsh`) to a custom
  curses-based (Python curses or urwid) TUI application. When that application
  exits, the session logs out; there is no bare shell to drop to.
- No hacking-minigame gate on login. Straight, real authentication (password or
  configured autologin) — the FO4 word-guessing minigame was explicitly
  rejected as a security mechanism.
- Single console/session — not multiple switchable TTY "stations." Everything
  lives inside one Home Hub with nested menus/sub-screens.

## 5. Home Hub Structure

The Home Hub is the top-level menu shown after login. All labels below are
placeholders — final wording will mix Vault-Tec/Aperture-style flavor with
plain practicality, and every label must be reviewed and approved by the user
before finalizing.

- **Programs** — general tools (file manager via ranger, media player via
  cmus/mpv, system monitor via btop, etc.)
- **Recreation** — dedicated games area. Genre direction: roguelikes (nethack,
  DCSS), arcade/simple (snake, tetris-likes, invaders), puzzle/strategy (chess,
  2048-likes). Specific title list TBD.
- **Functions Control** — real, functional system toggles only. No
  cosmetic/fake elements. Covers: brightness (including synced dual-panel
  brightness), second-screen on/off, power profile switching.
- **Settings** — system resource limits, network configuration, user/auth
  settings, theme/sound customization, and overseer (Frank) sensitivity tuning
  for detection thresholds only. Frank's core config, logs, and functions are
  explicitly excluded from Settings and unreachable by any user from within the
  running OS.
- **Log** — two distinct, separate sections:
  - Real system logs (journalctl, kernel, auth) — raw and unmodified
  - Frank's own incident log — see Section 6, this is heavily restricted
- **Personal Notes** — user's own space. Structure: a quick dated/chronological
  journal plus a separate tagged/organized notes section. Not
  monitored/exempted status was considered and explicitly dropped — this space
  is not exempt from Frank's monitoring.
- **AI Chat** — a separate, general-purpose assistant (Mistral API), distinct
  from Frank, for everyday questions. Its own dedicated menu item, called
  on-demand only (not automatically) to control cost.

## 6. Frank (The Overseer)

### Identity

- **Name:** Frank (from "I'm going to be frank with you")
- **Personality:** corporate/menacing — cold, procedural, faintly threatening.
  Not comic-relief snark; more "this is being recorded and evaluated" in tone.

### Data Sources (full scope, no exempt zones)

- Shell/command history
- Running processes and resource usage
- Filesystem activity (files opened/edited)
- Network activity (connections/destinations, and what is being
  searched/requested from the browser program and other places)
- Essentially everything this user does.

### Detection Engine — Hybrid

- **Rule-based layer** (offline, fast, predictable): pattern/keyword matching
  against the real data sources above. This is the primary, always-on detection
  mechanism.
- **AI layer** (Mistral API): only invoked on flagged/ambiguous events
  identified by the rule-based layer — not polling continuously — to keep
  monthly cost under ~$10–20. Writes the actual commentary/phrasing; does not
  independently decide what counts as a violation.
- **Two category tracks**, each with their own severity tiers:
  - Security/resource-focused (malware, unsafe scripts, exploit tooling,
    credential exposure, runaway resource usage)
  - Legal/ethical-focused (broader concerning content or activity)
- AI Chat (Mistral) is architecturally separate from Frank — same provider,
  different purpose, different invocation pattern.
- Local-model fallback should be architected as a future option (e.g. if ported
  to a desktop PC with more compute), even if not implemented in v1.

### Warnings & Lockouts

- Warnings escalate, scaled by severity — serious flags skip straight to fewer
  warnings before action; minor flags get more warnings first.
- Delivery: status bar notification for normal warnings; full-screen
  interrupting banner for serious-severity warnings.
- Lockout scope is severity-based:
  - Minor: current session/console only
  - Serious: whole machine
- Recovery model:
  - A hard timed cooldown is the absolute ceiling on any lockout — it always
    eventually expires, no exceptions.
  - Frank may extend a lockout within that ceiling for severe violations (i.e.
    make it take longer, up to the max), but can never override or exceed the
    hard timer.
  - Manual override is available but must be verified by Frank, not a simple
    bypass.
- Nothing about the enforcement system is cosmetic/fake — no fictional
  "lockdown" theater. Everything Functions Control and Frank do is real.

### Frank's Incident Log (visible ledger)

- Triggered on/off by keyboard detachment: second screen (normally off) turns
  on automatically when the keyboard is undocked, and turns back off
  automatically when the keyboard is reattached.
- What's shown: the same raw stream Frank uses internally, piped directly to the
  screen (no separate redacted copy — most efficient, single source of truth).
- Content shown to the user is restricted to **timestamps only** — dates and
  times of logged actions, formatted for efficient machine parsing/writing, not
  formatted for casual human readability. No categories, no severity tags, no
  descriptions, no content.
- All actual finding detail — what was flagged, why, contents — is Frank-only
  and never surfaced to any user through any interface. This is a deliberate
  design choice: the user should not be able to see or reason about specifics of
  what tripped a flag.

### Context/Memory Management

- Daily reset applies to both Frank's working AI context and the visible
  timestamp ledger.
- Severity does not extend memory/context retention — it only extends how long
  an active lockout/restriction lasts (within the hard timer ceiling described
  above). Keep this distinction clean in implementation: severity → lockout
  duration; time-of-day → context/ledger reset.

### Config Protection

- Frank's configuration, thresholds (beyond the limited Settings-exposed
  sensitivity tuning), logs, and internal functions must be blocked from
  modification or access by any user from within the running OS — no sudo path,
  no config file editable by the user account, no way to kill or disable the
  Frank process from a normal session.
- Explicitly acknowledged limitation: this is high-friction protection against
  in-session tampering, not literal immunity to someone with physical access and
  a USB boot disk. A stronger hardening pass (e.g. disk encryption) has been
  deferred to a later phase at the user's request — do not over-engineer this in
  v1.

## 7. Hardware-Specific Adaptations (Zenbook Duo)

- Source reference: `alesya-h/zenbook-duo-2024-ux8406ma-linux` (community
  project, originally built around GNOME).
- **Port, don't assume-compatible:** the kernel/udev/sysfs-level pieces
  (backlight sync via `backlight=card1-eDP-2-backlight`, iio-sensor-proxy for
  rotation, libwacom files for the bottom panel's pen/touch digitizer, battery
  limiter) are GNOME-agnostic and should port directly.
- **Replace GNOME-specific glue:** the "GNOME session watcher" scripts
  (`duo watch-displays`, `duo watch-rotation`, and the
  `gnome-monitor-config`-based screen toggling) need to be reimplemented against
  `wlr-randr` / cage's compositor instead.
- **Keyboard detach/attach detection:** reuse this existing mechanism as the
  trigger for Frank's ledger screen (Section 6), not just for display topology
  changes.
- **Security fix required:** the original project's brightness-control approach
  uses a blanket NOPASSWD sudo rule on `/usr/bin/env`, which is a broad
  privilege-escalation hole. Replace with a properly scoped polkit rule or a
  minimal setuid helper limited to the specific backlight sysfs path.

## 8. Sound Design

Full retro-computer soundscape: boot chimes, ambient hum, error buzzes, on top
of visual/keypress feedback.

## 9. Explicitly Rejected / Out of Scope for v1

- FO4-style word/bracket hacking minigame as any kind of login or access gate
- Multiple switchable TTY "stations" (simplified to single console)
- Fictional/themed boot splash (real log only, no added flavor)
- Fake/cosmetic security theater in Functions Control or lockouts
- Exempt/private zone immune from Frank's monitoring
- Idle screensaver behavior (terminal just sits when untouched)
- USB-boot-proof tamper resistance (deferred, not in scope yet)

## 10. Still Open — Needs Resolution Before or During Build

- Exact rule-based trigger definitions/keyword-pattern lists for both category
  tracks and their severity tiers
- Specific game title list for Recreation
- Frank's actual voice lines / commentary style guide (corporate/menacing tone
  established, specific phrasing not yet drafted)
- Final wording for all menu labels (user will review/approve all of them)
- Precise Settings-exposed range for Frank sensitivity tuning (what's adjustable
  vs. hard-locked)

## 11. Suggested Build Order

1. Base Arch install, linux-lts, minimal package set
2. Verify second-screen behavior on chosen kernel before going further
3. cage + kitty kiosk layer, confirm boots straight past any DM
4. Plymouth text theme, GRUB param cleanup
5. Custom curses TUI shell (Home Hub nav skeleton, no content yet)
6. Port/adapt Zenbook Duo hardware scripts (display, brightness, battery,
   keyboard detach event → hook available for later Frank integration)
7. Fix NOPASSWD sudo issue with proper polkit rule
8. Build out Home Hub sub-areas one at a time: Functions Control → Settings →
   Programs → Personal Notes → Log (real system log side first, Frank's side
   stubbed) → Recreation → AI Chat
9. Build Frank: rule-based detection engine first (offline, testable), then
   Mistral API integration for commentary, then warning/lockout enforcement,
   then the restricted visible ledger tied to keyboard-detach
10. Sound design and CRT visual theme pass
11. Full-system stability/soak testing before treating it as daily-driver stable
