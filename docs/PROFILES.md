# Hardware profiles

The core of this repo — `hub/` (the Home Hub TUI), `frank/` (the overseer
daemon), `system/`, `theme/`, `sounds/`, and `install/00`–`06` — targets no
specific device. It's a generic console kiosk: cage+kitty running a curses
TUI as the login shell, with Frank watching in the background. Any x86_64
machine that can run Arch Linux and a Wayland compositor can run the core.

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
  hardware/       helper scripts/binaries, installed to /usr/local/lib/zenhub/
                  (the Hub calls into this dir via ZENHUB_HW_BIN — see
                  hub/zenhub/session.py — with graceful "not installed"
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

## Existing profiles

- **`zenbook-duo-2024`** — Asus Zenbook Duo 2024 (UX8406MA), Intel Meteor
  Lake, dual eDP panels, detachable BT keyboard. The original target device
  this project was built for; see `profiles/zenbook-duo-2024/README.md`.

## Adding a new profile

Copy the shape above. Keep every device assumption inside `profiles/<name>/`
— nothing in `hub/`, `frank/`, `install/00`–`06`, or `system/` should ever
need to know a specific device exists. If you find yourself wanting to add a
device check to core code, that's a signal the feature belongs in
`hub/zenhub/session.py`'s hardware-helper indirection (call an external
binary, degrade gracefully if it's missing) rather than as a branch in the
core.
