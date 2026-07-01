# Zenbook Duo Terminal OS

A fully console-based Arch Linux system for the 2024 Asus Zenbook Duo
(UX8406MA). No desktop environment, no window-manager chrome, no typed shell
commands in normal use. The machine is navigated like a Fallout&nbsp;4 terminal
or an Aperture Science console: **highlight an option, press Enter.**

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
- **Hardware ports** (`hardware/`) — Zenbook Duo glue (display topology,
  brightness sync, keyboard detach, rotation, battery limit) reimplemented
  against `wlr-randr`/`cage` instead of GNOME.
- **Theme + sound** (`theme/`, `sounds/`) — amber/green CRT phosphor look and
  the retro soundscape.
- **Docs** (`docs/`) — the full build spec, architecture, and the running list
  of decisions awaiting your approval.

## Target hardware

- Asus Zenbook Duo 2024 (**UX8406MA**), Intel Meteor Lake
- Dual eDP panels: `eDP-1` (top/primary), `eDP-2` (bottom/secondary)
- Detachable Bluetooth keyboard
- Kernel: `linux-lts`, pinned (see `install/01-kernel-lts.sh` for the
  second-screen i915 regression rationale)

## Quick start (on the target machine)

> Do a minimal Arch base install first (`pacstrap` base + `linux-lts`), boot
> it, then:

```sh
git clone <this-repo> /opt/zenbook-terminal-os
cd /opt/zenbook-terminal-os
sudo ./install/run-all.sh        # or run install/NN-*.sh individually
```

Each install script is idempotent and prints what it will do. Read
[`docs/INSTALL.md`](docs/INSTALL.md) before running anything.

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
install/     Ordered, idempotent installer scripts + package lists
system/      Files copied onto the target root (/etc, /usr/local, ...)
hub/         zenhub — the curses login-shell TUI (Home Hub)
frank/       frankd — the overseer daemon (rules, enforcement, ledger, AI)
hardware/    Zenbook Duo hardware glue ported to wlr-randr/cage
theme/       kitty/foot config, CRT palettes, Plymouth text theme
sounds/      Retro soundscape assets + playback hooks
```
