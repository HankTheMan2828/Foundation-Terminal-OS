# Hardware profile: zenbook-duo-2024

The device-specific glue for the Asus Zenbook Duo 2024 (**UX8406MA**), Intel
Meteor Lake. This is what the generic Foundation TerminalOS core (`hub/`, `frank/`,
`install/00`–`06`) becomes a *release* for this laptop, per
[`../../docs/PROFILES.md`](../../docs/PROFILES.md).

## What it targets

- Dual eDP panels: `eDP-1` (top/primary), `eDP-2` (bottom/secondary)
- Detachable Bluetooth keyboard
- Known i915 regression on the bottom panel for mainline kernels 6.9+
  (last confirmed-good: 6.8.12) — see the manual gate this script prints

## What it adds on top of the core

- `packages.txt` — `iio-sensor-proxy`, `libwacom`, `brightnessctl`
- `hardware/` — helper scripts installed to `/usr/local/lib/zenhub/`, invoked
  by the Hub via `ZENHUB_HW_BIN` (see `hub/zenhub/session.py`): display
  topology (`duo-watch-displays`, `duo-screen-toggle`), keyboard detach
  (`duo-keyboard-detach`), backlight sync (`backlight-sync`), battery limiter
  (`duo-battery-limit`)
- `system/etc/udev/rules.d/90-zenbook-duo.rules` — keyboard detach/attach
  event + eDP-2 backlight sysfs naming
- `system/etc/polkit-1/rules.d/50-zenbook-backlight.rules` — scoped backlight
  authorization (replaces the community project's blanket `NOPASSWD` sudo hole)
- `system/etc/systemd/system/duo-battery-limit.service`,
  `duo-hardware.service` — battery charge limit + display topology watcher
- `system/etc/systemd/system/frank-ledger.service` — pipes Frank's
  timestamp-only ledger to eDP-2 on keyboard detach (spec §6); this is the one
  Frank-adjacent unit that lives here rather than in `frank/`, because it only
  means anything on a device with a second panel to pipe it to

Ported from `alesya-h/zenbook-duo-2024-ux8406ma-linux`, with the GNOME session
glue replaced by `wlr-randr`/`cage` calls (see `../../docs/ARCHITECTURE.md`).

## Using it

```sh
HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh
```

or run the core steps individually, then:

```sh
sudo HARDWARE_PROFILE=zenbook-duo-2024 ./install/07-hardware-profile.sh
```

Reversed by `install/uninstall.sh` (calls `uninstall.sh` in this directory
when `HARDWARE_PROFILE=zenbook-duo-2024` is set).

## Known gaps (spec `TODO(hardware)`)

- The detachable keyboard's Bluetooth VID:PID in `90-zenbook-duo.rules` is a
  placeholder (`0b05:XXXX`) — fill in from `udevadm monitor` on the real unit.
- `backlight-sync` assumes `card1-eDP-2-backlight`; verify against
  `ls /sys/class/backlight/` on the target and adjust if it differs.
- None of this has been exercised on the physical hardware yet — see
  `../../docs/STATUS.md`.
