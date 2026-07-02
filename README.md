# Foundation TerminalOS

*From the Foundation.*

A fully console-based Arch Linux system. This is the parent project: a
generic core that targets no specific device — any x86_64 machine that can
boot Linux to a text console works; there is **no GPU, compositor, or
graphical-terminal requirement** — from which per-device **hardware
profiles** are built and refined (see [`docs/PROFILES.md`](docs/PROFILES.md)).
It ships with one profile so far, for the 2024 Asus Zenbook Duo (UX8406MA),
which is where the project started. No desktop environment, no window-manager
chrome, no typed shell commands in normal use. The machine is navigated like a
Fallout&nbsp;4 terminal or an Aperture Science console: **highlight an option,
press Enter.**

Boot lands on a terminal-styled **login screen** — these are shared company
machines, up to 8 tiered accounts each with a fixed storage allotment (see
[`docs/USERS.md`](docs/USERS.md)) — and from there into a custom curses TUI
(the "Home Hub") that *is* the login shell: there is no bash prompt to fall
back to. An always-on monitoring/accountability layer, **Frank**, watches real
system usage per user and can restrict access based on rule-based detection
plus AI-generated commentary. All user-facing applications are being built
in-house; the few remaining open-source stand-ins are marked for replacement.

> **Status:** early scaffold. This repository is the *deployable source and
> installer* for the OS. It is built and iterated on off-device, then cloned
> onto the target Arch install and applied with the scripts in `install/`.
> See [`docs/STATUS.md`](docs/STATUS.md) for what is real vs. stubbed today.

---

## What this repo is

This is **not** a disk image. It is a set of:

- **Install scripts** (`install/`) — run in order on a fresh, minimal Arch
  base to turn it into Foundation TerminalOS.
- **System files** (`system/`) — configs, systemd units, polkit rules, and
  udev rules that get copied onto the target under `/`.
- **The Home Hub** (`hub/`) — the curses TUI that serves as the login shell.
  Core apps (notes, file manager, system monitor) live here as native
  screens.
- **Frank** (`frank/`) — the overseer daemon: rule engine, enforcement,
  ledger, optional Mistral commentary.
- **Games** (`games/`) — standalone in-house TUI programs launched from the
  Hub's Recreation area: Foundation Arcade (Snake, Falling Blocks, 2048,
  Sudoku, Invaders) and Foundation Chess today; a two-vintage Rogue
  re-implementation plus a modernized "Foundation Depths" are designed
  (see [`docs/ROGUELIKE-DESIGN.md`](docs/ROGUELIKE-DESIGN.md)) and awaiting
  approval before build.
- **Media** (`media/`) — Foundation Media, the in-house audio player,
  launched the same way.
- **Hardware profiles** (`profiles/`) — optional, per-device glue (display
  topology, brightness sync, keyboard detach, rotation, battery limit),
  applied only when selected. The core never depends on one existing. See
  [`docs/PROFILES.md`](docs/PROFILES.md).
- **Theme + sound** (`theme/`, `sounds/`) — amber/green CRT phosphor look and
  the retro soundscape.
- **Docs** (`docs/`) — the full build spec, architecture, and the running list
  of decisions awaiting your approval.

## Target hardware

The core (`install/00`–`06`) assumes nothing beyond "x86_64 machine that can
boot Arch Linux to the kernel text console." The Hub draws with curses on the
VT the same way DOS programs drew on the BIOS console — no GPU driver, no
Wayland, no X. Device-specific hardware is opt-in via a profile:

- **`zenbook-duo-2024`** — Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor
  Lake, dual eDP panels (`eDP-1` top, `eDP-2` bottom), detachable Bluetooth
  keyboard, plus the manual kernel-regression gate that only applies to this
  device. Its dual-panel glue needs a Wayland session (`wlr-randr`), so this
  profile — and only this profile — installs a cage+kitty display stack as a
  plugin. See [`profiles/zenbook-duo-2024/README.md`](profiles/zenbook-duo-2024/README.md).

With no profile selected you get the generic kiosk core with no laptop-specific
services, udev rules, or polkit grants installed.

Hardware profiles solve *which device*, not *how powerful a device*: the core
still assumes an MMU-capable CPU and enough RAM for systemd + CPython — but
nothing graphical, so cheap SBC-class x86 boxes and thin clients qualify.
The standing direction is DOS-grade minimalism, in two further steps: a
**lean base** (Alpine/busybox, no systemd — MB-class RAM, same code) and
**Pocket8086** (real-mode 16-bit x86, KB-class RAM — a from-scratch
implementation in the MS-DOS mold, since Linux/Python physically cannot go
there; design-doc-first). See "Capability tiers" in
[`docs/PROFILES.md`](docs/PROFILES.md) and [`docs/BUILD-QUEUE.md`](docs/BUILD-QUEUE.md) §6.

## Quick start (on the target machine)

> Do a minimal Arch base install first (`pacstrap` base + `linux-lts`), boot
> it, then:

```sh
git clone <this-repo> /opt/terminal-os
cd /opt/terminal-os
sudo ./install/run-all.sh        # generic core only

# or, building a release for a specific device:
HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh
```

Each install script is idempotent and prints what it will do. Read
[`docs/INSTALL.md`](docs/INSTALL.md) and [`docs/PROFILES.md`](docs/PROFILES.md)
before running anything.

## Try the Home Hub without installing

The Hub is pure-stdlib Python curses, so you can run the nav skeleton on any
machine:

```sh
python3 -m foundationhub            # from inside hub/, or with hub/ on PYTHONPATH
```

And Frank's offline rule engine is unit-tested with no external services:

```sh
cd frank && python3 -m pytest
```

The in-house games and media player also run off-device (pure-stdlib,
`windows-curses` on Windows):

```sh
cd games && python3 -m pytest              # game logic: arcade + chess, curses-free
cd games && python3 -m foundation_arcade   # or: python3 -m foundation_chess
cd media && python3 -m pytest         # playlist/library/PCM/decoder logic
cd media && python3 -m foundationmedia
```

## Design decisions still open

Menu wording, Frank's voice lines, rule/keyword lists, and the game list are
all **drafted for your review, not finalized**. See
[`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md). Nothing user-facing is
locked until you sign off. The roguelike specifically has its own design
doc, [`docs/ROGUELIKE-DESIGN.md`](docs/ROGUELIKE-DESIGN.md), with six open
items mirrored in `OPEN-QUESTIONS.md` §11 — no code exists yet.

## Repository layout

```
docs/        Spec, architecture, install guide, open decisions, status
install/     Ordered, idempotent installer scripts + package lists (generic core)
system/      Files copied onto the target root (/etc, /usr/local, ...)
hub/         foundationhub — the curses login-shell TUI (Home Hub)
frank/       frankd — the overseer daemon (rules, enforcement, ledger, AI)
games/       Foundation Arcade, Foundation Chess, and (designed) the roguelike(s)
media/       foundationmedia — the in-house audio player
profiles/    Optional per-device hardware profiles (e.g. zenbook-duo-2024)
theme/       CRT palettes (kernel-VT font + colors), Plymouth text theme
sounds/      Retro soundscape assets + playback hooks
```
