# Hardware profiles

The core of this repo — `hub/` (the Home Hub TUI), `frank/` (the overseer
daemon), `system/`, `theme/`, `sounds/`, and `install/00`–`06` — targets no
specific device. It's a generic console kiosk: a curses TUI running as the
login shell **directly on the kernel text console (VT)**, with Frank watching
in the background. There is no compositor, no graphical terminal, and no
GPU/DRM requirement in the core — any x86_64 machine that can boot Arch Linux
to a text console can run it. A device that genuinely needs a display stack
gets one from its profile (see the display-stack hook below).

Actual laptops have quirks — display topology, backlight sysfs names,
detach/rotate sensors, kernel regressions. Those live under `profiles/`, one
directory per device, and are **only** applied when you explicitly select one.
Building for a specific machine — pinning a profile, tuning its glue, shipping
it — is what turns the generic core into a *release* for that hardware.

## Mechanism

`install/07-hardware-profile.sh` is the only place the core knows profiles
exist. It's a no-op unless `HARDWARE_PROFILE` is set:

```sh
HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh
```

With no `HARDWARE_PROFILE`, steps 00–06 install and configure the generic
kiosk core and step 07 prints a note and exits — you get a working Home Hub
and Frank on whatever hardware you're on, with no laptop-specific services,
udev rules, or polkit grants installed.

`install/uninstall.sh` mirrors this: if `HARDWARE_PROFILE` is set and the
profile has an `uninstall.sh`, it's run to reverse the profile's changes
before the generic recovery steps run.

## Anatomy of a profile

```
profiles/<name>/
  README.md       what hardware this targets, what it adds, known gaps
  packages.txt    packages this profile adds on top of install/packages.txt
  install.sh      applies the profile (packages, files, services); run as root,
                  invoked by install/07-hardware-profile.sh or standalone
  uninstall.sh    reverses install.sh
  hardware/       helper scripts/binaries, installed to /usr/local/lib/foundationhub/
                  (the Hub calls into this dir via FOUNDATIONHUB_HW_BIN — see
                  hub/foundationhub/session.py — with graceful "not installed"
                  fallback if a profile isn't applied)
  system/         files copied onto the target root: udev rules, polkit
                  rules, systemd units, mirroring the layout of the repo's
                  top-level system/ tree
```

A profile may also add its own systemd units that depend on core services
(e.g. a unit that reacts to a Frank event) — see
`profiles/zenbook-duo-2024/system/etc/systemd/system/frank-ledger.service`
for an example. This is why the hardware-profile step runs *last*
(`install/run-all.sh`): profile glue can assume the core is already in place.

### The display-stack hook

The core session is `getty → foundationhub-session → python -m foundationhub`
on the kernel VT — no display stack at all. If a device's glue truly requires
one (the Zenbook Duo drives its dual-panel topology through `wlr-randr`,
which needs a Wayland compositor), the profile installs an executable at
`/usr/local/lib/foundationhub/display-stack`; `foundationhub-session` execs it
instead of the direct console path when present. Its contract: end up running
`python -m foundationhub` fullscreen with no shell behind it, and exit when
the Hub exits. Removing the profile removes the file and the session falls
back to the plain VT. Nothing in the core knows what the stack is.

## Existing profiles

- **`zenbook-duo-2024`** — Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor
  Lake, dual eDP panels, detachable BT keyboard. The original target device
  this project was built for; see `profiles/zenbook-duo-2024/README.md`.

## Adding a new profile

Copy the shape above. Keep every device assumption inside `profiles/<name>/`
— nothing in `hub/`, `frank/`, `install/00`–`06`, or `system/` should ever
need to know a specific device exists. If you find yourself wanting to add a
device check to core code, that's a signal the feature belongs in
`hub/foundationhub/session.py`'s hardware-helper indirection (call an external
binary, degrade gracefully if it's missing) rather than as a branch in the
core.

## Capability tiers (operator-directed: run on anything, DOS-style)

Hardware profiles solve *device* portability (which laptop). Capability-class
portability (how powerful the machine has to be) is its own axis, and the
operator's standing direction is: **the closer to MS-DOS the better — no
faking, no emulating, boot to a text screen and work.** Targets, honestly
stated:

- **Tier 1 — the x86_64 Linux core (built; this repo).** The Hub on the
  kernel VT, no GPU/compositor/graphical anything. Floor is set by
  Linux + systemd + CPython, not by our code: practically a few hundred MB of
  RAM on the Arch base. That covers effectively every x86_64 box, thin
  client, and SBC made this century.
- **Tier 1-lean (planned next; same code).** Swap the base under the same
  Hub/Frank: Alpine/musl + openrc or a busybox initramfs instead of
  Arch + systemd. Same Python, same screens. Realistic floor drops to the
  low tens of MB — this is the "MB of RAM" target, and it's a packaging
  effort, not a rewrite.
- **Tier 2 — Pocket8086 / real-mode 16-bit (committed direction, not
  started).** "KB of RAM" and 16-bit x86 are **physically outside what any
  Linux can do** — no MMU-less 8086 runs a mainline kernel, and CPython
  won't fit in kilobytes. There is no configuration flag that gets there;
  pretending otherwise would be the faking we don't do. The honest path is
  the same one MS-DOS itself took: a from-scratch real-mode program in
  C/asm, booting from a floppy/BIOS or hosted on FreeDOS, driving BIOS
  text output directly — with the Hub's highlight-and-Enter UX and Frank's
  rule engine/enforcement/ledger reimplemented small (no GC, no runtime).
  Shares design and wording with this repo, zero code. Design-doc-first,
  like the roguelike (see `docs/BUILD-QUEUE.md` §6).
