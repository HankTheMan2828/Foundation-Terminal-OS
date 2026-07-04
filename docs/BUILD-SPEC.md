# Zenbook Duo Terminal OS — Build Specification

> This is the authoritative specification as provided. It is preserved verbatim
> as the source of truth. Implementation notes and decisions derived from it
> live in the other files in `docs/`.
>
> **Naming note (2026-07-01):** the system's official name is now
> **Foundation TerminalOS** — *"From the Foundation."* The title above is the
> spec's original working name, kept because this document is verbatim.
>
> **Implementation note:** the spec below was written around one device (§1,
> §7). The build keeps every device-specific requirement (kernel gate,
> `hardware/*`, polkit rule, systemd units for display/battery/ledger-on-detach)
> isolated in `profiles/zenbook-duo-2024/`, applied only when
> `HARDWARE_PROFILE=zenbook-duo-2024` is set. Everything else in this spec
> (§2–§6, §8–§10) is implemented as generic core with no device assumption.
> See [`PROFILES.md`](PROFILES.md).

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

- No display manager, no desktop environment, **no display stack at all in
  the core** (amended: this supersedes the original cage/kitty plan below).
- systemd boots to `multi-user.target` (no `graphical.target`).
- The Home Hub runs with curses **directly on the kernel text console (VT)**
  as the login shell. No compositor, no graphical terminal, no GPU/DRM
  requirement — the machine works like a DOS box: boot, text screen, done.
  No window chrome, no window switching, no multitasking surface beyond
  what's built into the nav system itself.
- *(Superseded original plan, kept for history: a Wayland kiosk compositor —
  cage — launching a single fullscreen kitty. That stack is now strictly a
  hardware-profile plugin: only a device whose glue needs a compositor
  installs it — see §7 and docs/PROFILES.md.)*
- Multi-monitor handling (enabling/disabling/positioning the second panel) is
  a hardware-profile concern, via **wlr-randr** inside that profile's own
  display stack — the generic core has a single console and no monitor glue.
- Visual theme: amber/green CRT phosphor look, scanlines, glow. Monospace
  bitmap-style font (e.g. Terminus or similar) — on the core this is the
  console font (`setfont`) plus the VT's retunable 16-color palette.

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

The Home Hub is the top-level menu shown after login. Wording mixes
Vault-Tec/Aperture-style flavor with plain practicality; every label is
reviewed and approved by the user (see `OPEN-QUESTIONS.md`).

> **IA rework (feedback #8, 2026-07-03).** The first-hardware-run feedback that
> the top level "felt a little hectic" drove a regrouping. The top level is now
> five entries — **Programs · Recreation · Settings · Logs · Power** — with two
> former top-level entries folded in: Notes moved *under* Programs (and the old
> duplicate note surfaces merged), and the read-only System Status readout moved
> *under* Settings. AI Chat is built but hidden from the menu for now.

- **Programs** — general tools, in order:
  - **Notes** — the operator's writing space, one page split by *purpose* into
    two sections: **Work** first, **Personal** last. Each is its own folder
    (`work/`, `personal/`) so the File Manager shows them as two clean folders.
    Each section has plain notes (named on creation) plus one dated feature —
    Work gets timestamped **Dated Entries** (several per day), Personal gets the
    one-page-per-day **Dated Journal**. Not exempt from Frank's monitoring
    (an exempt zone was considered and explicitly dropped).
  - **Notes Search** — a separate search program (text + `#tags`). Asks whether
    to include Personal notes; **defaults to Work-only**.
  - **File Manager** (in-house), **Media** (in-house `foundationmedia`),
    **System Monitor** (in-house, view-only).
- **Recreation** — dedicated games area (+ a system-wide **High Scores** board).
  Genre direction: roguelikes, arcade/simple, puzzle/strategy.
- **Settings** (was "Functions Control") — real, functional system toggles only,
  no cosmetic/fake elements: brightness (synced dual-panel), second-screen
  on/off, power profile, theme/sound, text size. Also holds the two
  config-shaped things that used to sit under Status: **Network** (`nmtui`) and
  the read-only **System Status** readout (logged-in user + uid, and a
  functioning/not list for network, audio, and the Frank overseer). No resource
  limits, no user/auth actions, no overseer sensitivity tuning — Frank's core
  config, logs, and functions remain excluded and unreachable from within the OS.
- **Logs** — two distinct, separate sections:
  - Real system logs (journalctl, kernel, auth) — raw and unmodified
  - Frank's own incident log — see Section 6, this is heavily restricted
- **Power** — log out (ends the session), reboot, shut down.
- **AI Chat** *(built, currently hidden)* — a separate, general-purpose
  assistant (Mistral API), distinct from Frank, for everyday questions. Called
  on-demand only (not automatically) to control cost. The screen exists; it is
  off the top-level menu pending the key decision, re-added by editing
  `screens/__init__.build_home`.

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
  `wlr-randr` / cage's compositor instead. (Amended: since the core no longer
  ships any display stack, the cage+kitty session itself is part of THIS
  profile — installed as its `display-stack` plugin — solely because this
  glue needs a Wayland compositor to drive.)
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
3. Console kiosk layer (kernel VT, no display stack), confirm boots straight
   past any DM
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
