# Terminal OS

A fully console-based Arch Linux system. This is the parent project: a
generic core that targets no specific device — any x86_64 machine that can
run Arch and a Wayland compositor works — from which per-device **hardware
profiles** are built and refined (see [`docs/PROFILES.md`](docs/PROFILES.md)).
It ships with one profile so far, for the 2024 Asus Zenbook Duo (UX8406MA),
which is where the project started. No desktop environment, no window-manager
chrome, no typed shell commands in normal use. The machine is navigated like a
Fallout&nbsp;4 terminal or an Aperture Science console: **highlight an option,
press Enter.**

Login drops straight into a custom curses TUI (the "Home Hub") that *is* the
login shell — there is no bash prompt to fall back to. An always-on
monitoring/accountability layer, **Frank**, watches real system usage and can
restrict access based on rule-based detection plus AI-generated commentary.

> **Status:** early scaffold. This repository is the *deployable source and
> installer* for the OS. It is built and iterated on off-device, then cloned
> onto the target Arch install and applied with the scripts in `install/`.
> See [`docs/STATUS.md`](docs/STATUS.md) for what is real vs. stubbed today.

---

## What this repo is

This is **not** a disk image. It is a set of:

- **Install scripts** (`install/`) — run in order on a fresh, minimal Arch
  base to turn it into the Terminal OS.
- **System files** (`system/`) — configs, systemd units, polkit rules, and
  udev rules that get copied onto the target under `/`.
- **The Home Hub** (`hub/`) — the curses TUI that serves as the login shell.
- **Frank** (`frank/`) — the overseer daemon: rule engine, enforcement,
  ledger, optional Mistral commentary.
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
run Arch Linux and a Wayland kiosk compositor." Device-specific hardware is
opt-in via a profile:

- **`zenbook-duo-2024`** — Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor
  Lake, dual eDP panels (`eDP-1` top, `eDP-2` bottom), detachable Bluetooth
  keyboard, plus the manual kernel-regression gate that only applies to this
  device. See [`profiles/zenbook-duo-2024/README.md`](profiles/zenbook-duo-2024/README.md).

With no profile selected you get the generic kiosk core with no laptop-specific
services, udev rules, or polkit grants installed.

Hardware profiles solve *which device*, not *how powerful a device*: the core
still assumes an MMU-capable CPU, a GPU/DRM driver for the Wayland compositor,
and enough RAM for systemd + CPython — workstation-class hardware. Two lower
capability tiers are planned but not yet built: a console-mode backend that
drops the Wayland/GPU requirement for cheap SBCs and thin clients, and a
from-scratch embedded port for sub-MMU hardware. See "Future portability
tiers" in [`docs/PROFILES.md`](docs/PROFILES.md).

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
python3 -m zenhub            # from inside hub/, or with hub/ on PYTHONPATH
```

And Frank's offline rule engine is unit-tested with no external services:

```sh
cd frank && python3 -m pytest
```

## Design decisions still open

Menu wording, Frank's voice lines, rule/keyword lists, and the game list are
all **drafted for your review, not finalized**. See
[`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md). Nothing user-facing is
locked until you sign off.

## Repository layout

```
docs/        Spec, architecture, install guide, open decisions, status
install/     Ordered, idempotent installer scripts + package lists (generic core)
system/      Files copied onto the target root (/etc, /usr/local, ...)
hub/         zenhub — the curses login-shell TUI (Home Hub)
frank/       frankd — the overseer daemon (rules, enforcement, ledger, AI)
profiles/    Optional per-device hardware profiles (e.g. zenbook-duo-2024)
theme/       kitty/foot config, CRT palettes, Plymouth text theme
sounds/      Retro soundscape assets + playback hooks
```
