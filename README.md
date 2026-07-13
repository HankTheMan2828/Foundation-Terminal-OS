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
(the **Home Hub**) that *is* the login shell: there is no bash prompt to fall
back to. An always-on monitoring/accountability layer, **Frank**, watches real
system usage per user and can restrict access based on rule-based detection
plus optional AI-assisted sensing and commentary. User-facing applications are
built in-house (notes, files, monitor, media, arcade, chess); the few remaining
upstream stand-ins are intentional exceptions (classic Rogue) and are documented
as such.

> **Status:** **v0.1.0 — first stable line** (`0.1.x`). The deployable
> source, install scripts, ISO pipeline, Home Hub, Frank, games, media, and
> update system are in-tree and unit-tested off-device (~450 tests). Hardware
> soak and a few polish items remain open; see [`docs/STATUS.md`](docs/STATUS.md)
> for the working-vs-stub table, [`docs/VERSIONING.md`](docs/VERSIONING.md) for
> the release naming scheme, and
> [`tools/screenshots/preview/`](tools/screenshots/preview/) for CRT-styled
> captures of the live Hub (dev harness — not part of the OS).

---

## What this repo is

The deployable source for the OS, plus the pipeline that packages it into a
flashable installer:

| Area | Path | Role |
|------|------|------|
| Installer ISO | `image/` | Bootable ISO that embeds this repo + an offline package repo. Flash, boot, install. See [`image/README.md`](image/README.md). |
| Install scripts | `install/` | Ordered, idempotent scripts (`00`–`11`) that turn a minimal Arch base into Foundation TerminalOS — also what the ISO runs in the target chroot. |
| System files | `system/` | Configs, systemd units, polkit rules, and udev rules copied onto the target under `/`. |
| Home Hub | `hub/` | `foundationhub` — curses login-shell TUI. Native screens for notes, files, monitor, assistant, status, logs, updates, and Frank negotiation. |
| Frank | `frank/` | `frankd` — overseer daemon: rules, Overseer Rulebook, enforcement, ledger, Hub activity feed, optional local/cloud AI sensor. |
| Games | `games/` | Foundation Arcade (Snake, Falling Blocks, 2048, Sudoku, Invaders) and Foundation Chess — standalone in-house TUIs. |
| Rogue (exception) | `vendor/` | Classic Rogue 1981 built from vendored source at ISO time. Rogue 1985 is a downloadable skeleton only — see [`docs/ROGUE-DOWNLOADABLE.md`](docs/ROGUE-DOWNLOADABLE.md). A modernized in-house roguelike (“Foundation Depths”) remains design-only ([`docs/ROGUELIKE-DESIGN.md`](docs/ROGUELIKE-DESIGN.md)). |
| Media | `media/` | Foundation Media — in-house audio player (stdlib WAV + ctypes ALSA; optional ffmpeg for broad formats). |
| Hardware profiles | `profiles/` | Optional per-device glue (display topology, brightness, keyboard detach, …). Core never depends on one existing. |
| Theme + sound | `theme/`, `sounds/` | CRT phosphor look (console font/palette + Plymouth text) and retro soundscape hooks. |
| Update system | `install/10`, Hub Settings | USB UPDATE mode in the installer + on-demand network updates from Settings (technician-gated). See [`docs/UPDATE-SYSTEM.md`](docs/UPDATE-SYSTEM.md). |
| Tools | `tools/` | USB creators (Windows / Unix) and off-device screenshot harness. |
| Docs | `docs/` | Spec, architecture, install guide, status, versioning, profiles, open decisions. |

## What's in the box (software)

Working off-device today (no target machine required for the TUIs and tests):

- **Login + multi-user** — up to 8 tiered accounts, password auth, storage
  readout and Frank violation counts on the roster
  ([`docs/USERS.md`](docs/USERS.md)).
- **Home Hub** — top level: **Programs · Recreation · Settings · Logs · Power**.
  - **Programs:** Notes (tabbed journal/notes + search), File Manager
    (quota-scoped), Media, System Monitor, Text Editor, on-device **Assistant**
    (same local model stack as Frank, separate trust domain).
  - **Recreation:** Arcade, Chess, Rogue (1981), High Scores.
  - **Settings:** System Status, network (`nmtui`), system update, hardware
    functions where present.
  - **Logs:** public Frank surfaces (timestamps / lock status only — never
    findings detail).
- **Frank** — rule engine + Overseer Rulebook (deterministic verdicts), Hub
  activity feed (so Frank is not blind without a shell), per-user enforcement,
  session vs. machine lockouts, **negotiable session locks** (machine/serious
  never), and a **local AI sensor by default** (BitNet b1.58 2B4T via
  `bitnet.cpp` / `frank-ai.service` — sensor only; the Rulebook decides guilt).
  See [`docs/FRANK-LOCAL-AI.md`](docs/FRANK-LOCAL-AI.md) and
  [`docs/FRANK-VOICE.md`](docs/FRANK-VOICE.md).
- **Update system** — USB path preserves homes, accounts, Frank state; network
  path is on-demand and setup-code gated. No polling daemon.
- **Install / ISO** — full archiso pipeline and live installer TUI written;
  not yet soak-tested on hardware.

Still open or deferred: CRT sound/visual asset polish, hardware soak, signing
policy for updates, browser collector for Frank, and the Foundation Depths
roguelike (design only). Tracked in [`docs/STATUS.md`](docs/STATUS.md) and
[`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md).

## Target hardware

The core (`install/00`–`06`, plus games/media/update/AI stages) assumes nothing
beyond “x86_64 machine that can boot Arch Linux to the kernel text console.”
The Hub draws with curses on the VT the same way DOS programs drew on the BIOS
console — no GPU driver, no Wayland, no X. Device-specific hardware is opt-in
via a profile:

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
there; design-doc-first). See “Capability tiers” in
[`docs/PROFILES.md`](docs/PROFILES.md) and [`docs/BUILD-QUEUE.md`](docs/BUILD-QUEUE.md) §6.

## Quick start — make an install USB (recommended, no prerequisites)

Nothing needs to be installed first — not Arch, not Linux. The installer ISO
carries the whole OS plus an offline copy of every package, and any ordinary
PC (Windows, macOS, or Linux) can write it to a USB stick:

1. **Get the ISO** — download `foundation-terminalos-<date>-x86_64.iso` from
   the [Releases page](https://github.com/HankTheMan2828/Foundation-Terminal-OS/releases)
   (CI builds it automatically), or build it yourself with
   `sudo ./image/build-iso.sh` (Arch or the Docker one-liner in
   [`image/README.md`](image/README.md)).
2. **Write the USB stick** with the creator in
   [`tools/usb-creator/`](tools/usb-creator/README.md): on Windows,
   double-click `FoundationUSBCreator.cmd` (it can download the ISO and stage
   Frank’s local AI model beside it); on macOS/Linux,
   `sudo ./tools/usb-creator/create-foundation-usb.sh`. Rufus/Etcher/Ventoy/`dd`
   work too.
3. **Boot the target machine from the stick** (boot-menu key at power-on —
   usually F12, F11, Esc, F2, or Del) and follow the on-screen installer. It
   partitions the disk (gated behind typing `ERASE`), installs everything
   offline, and reboots into the Home Hub.

See [`docs/INSTALL.md`](docs/INSTALL.md) for the full walkthrough, including
UPDATE mode on a machine that already has Foundation TerminalOS.

## Quick start — script install onto an existing Arch base (developers)

> The manual path, for iterating on the OS from a shell. Do a minimal Arch
> base install first (`pacstrap` base + `linux-lts`), boot it, then:

```sh
git clone <this-repo> /opt/terminal-os     # any path works; it's recorded at
cd /opt/terminal-os                        # install time, not assumed after
sudo ./install/run-all.sh        # generic core only

# or, building a release for a specific device:
HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh
```

Each install script is idempotent and prints what it will do. Stages cover
base packages, kernel, console kiosk, Plymouth/GRUB, Hub, Frank, theme/sound,
optional hardware profile, games, media, update system, and Frank local AI
(`install/11-frank-ai.sh`). Read [`docs/INSTALL.md`](docs/INSTALL.md) and
[`docs/PROFILES.md`](docs/PROFILES.md) before running anything.

## Try the Home Hub without installing

The Hub is pure-stdlib Python curses, so you can run it on any machine
(`windows-curses` on Windows):

```sh
cd hub && python3 -m foundationhub
# Dev knobs:
#   FOUNDATIONHUB_USERS=<path>   writable account registry
#   FOUNDATIONHUB_USER=<name>    skip login
#   FOUNDATIONHUB_DATA=<path>    per-user data root
```

Register an account (setup code `1234` for tiers above guest) and explore.

Frank’s offline rule engine and the rest of the suites are unit-tested with
no external services:

```sh
cd frank && python3 -m pytest     # ~150 tests (AF_UNIX IPC tests skip off-Linux)
cd hub   && python3 -m pytest     # ~191 tests
cd games && python3 -m pytest     # ~66 tests (arcade + chess, including perft)
cd media && python3 -m pytest     # ~41 tests
python3 -m frankd.rules --selftest
```

Games and media also run off-device:

```sh
cd games && python3 -m foundation_arcade   # or: python3 -m foundation_chess
cd media && python3 -m foundationmedia     # empty library first run; no ALSA off-target
```

Preview PNGs of real Hub screens (amber CRT renderer over a live TUI):
[`tools/screenshots/preview/`](tools/screenshots/preview/).

## Design decisions

Primary menu labels are **locked** (see `hub/foundationhub/labels.py` and
`docs/OPEN-QUESTIONS.md` §1). Remaining open items — update signing, roguelike
build approval, some AI-role model choices, and polish details — live in
[`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md). The roguelike has its own
design doc, [`docs/ROGUELIKE-DESIGN.md`](docs/ROGUELIKE-DESIGN.md); no
Foundation Depths code exists yet.

## Repository layout

```
docs/        Spec, architecture, install guide, open decisions, status
image/       Flashable installer-ISO pipeline (archiso profile + build script)
install/     Ordered, idempotent installer scripts 00–11 + package lists
system/      Files copied onto the target root (/etc, /usr/local, ...)
hub/         foundationhub — curses login-shell TUI (Home Hub)
frank/       frankd — overseer (rules, Overseer, enforcement, ledger, AI sensor)
games/       Foundation Arcade + Foundation Chess
vendor/      Vendored Rogue 1981 source + PKGBUILD (ISO offline-repo build)
media/       foundationmedia — in-house audio player
profiles/    Optional per-device hardware profiles (e.g. zenbook-duo-2024)
theme/       CRT palettes (kernel-VT font + colors), Plymouth text theme
sounds/      Retro soundscape assets + playback hooks
tools/       USB creators + temporary off-device screenshot harness
```

## Further reading

| Doc | Contents |
|-----|----------|
| [`docs/STATUS.md`](docs/STATUS.md) | What’s real vs. stubbed, build-order table |
| [`docs/VERSIONING.md`](docs/VERSIONING.md) | Release tags (`v0.1.x`) and legacy scheme |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Boot chain, processes, Frank isolation |
| [`docs/BUILD-SPEC.md`](docs/BUILD-SPEC.md) | Requirements / original build spec |
| [`docs/INSTALL.md`](docs/INSTALL.md) | USB and manual install walkthrough |
| [`docs/PROFILES.md`](docs/PROFILES.md) | Hardware profiles + capability tiers |
| [`docs/USERS.md`](docs/USERS.md) | Multi-user model and tiers |
| [`docs/UPDATE-SYSTEM.md`](docs/UPDATE-SYSTEM.md) | USB + network update design |
| [`docs/FRANK-LOCAL-AI.md`](docs/FRANK-LOCAL-AI.md) | On-device BitNet sensor + negotiation |
| [`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md) | Decisions awaiting sign-off |
| [`docs/BUILD-QUEUE.md`](docs/BUILD-QUEUE.md) | In-house app session specs (mostly landed) |
