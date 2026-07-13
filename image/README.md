# image/ — the flashable installer ISO

This directory turns the repo into a **bootable installer ISO**: flash it to a
USB stick, boot any x86_64 machine (a mini PC, a thin client, the Zenbook)
from it, and an on-screen installer — same phosphor-terminal register as the
OS — walks you through turning that machine into Foundation TerminalOS.

The ISO embeds two things at build time:

1. **this repo** at `/opt/terminal-os` inside the live image (a clean
   `git archive HEAD` snapshot), and
2. **an offline package repo** with every package the installed system needs
   — so installing on the target requires **no network at all**.

## Getting the ISO without building it

CI builds the ISO automatically (`.github/workflows/build-iso.yml`): every
semver tag (`v0.1.x`, … — see [`docs/VERSIONING.md`](../docs/VERSIONING.md))
gets a GitHub Release with the ISO attached, next to the USB creator programs
from [`tools/usb-creator/`](../tools/usb-creator/README.md). The workflow can
also be run by hand ("Run workflow") for a build artifact. End users should
start on the Releases page — no Arch machine involved anywhere.

## Building the ISO

Building uses [archiso](https://wiki.archlinux.org/title/Archiso), which only
runs on Arch. Two ways:

**On an Arch machine** (root, network required for the build itself):

```sh
pacman -S archiso grub      # grub: the uefi.grub boot mode runs grub-install on the host
sudo ./image/build-iso.sh
```

**Anywhere with Docker:**

```sh
docker run --privileged --rm -v "$PWD:/repo" archlinux:latest \
  bash -c 'pacman -Syu --noconfirm archiso grub git && /repo/image/build-iso.sh'
```

Output: `image/out/foundation-terminalos-<date>-x86_64.iso`.

Options:

- `--skip-offline-repo` — much smaller ISO, but the installer then needs
  network on the *target* machine.
- `BAKE_PROFILE=zenbook-duo-2024 ./image/build-iso.sh` — also bundle a
  hardware profile's extra packages into the offline repo. (Every profile's
  *code* is always embedded; this only matters for its package list.)

## Flashing

The friendly way, on any OS, is the USB creator in
[`tools/usb-creator/`](../tools/usb-creator/README.md) — double-click
`FoundationUSBCreator.cmd` on Windows, or
`sudo ./tools/usb-creator/create-foundation-usb.sh` on macOS/Linux. It only
offers removable USB disks and gates the write behind typing `ERASE`.

By hand:

```sh
lsblk                                        # find your USB stick — CAREFULLY
sudo dd if=image/out/foundation-terminalos-*.iso \
        of=/dev/sdX bs=4M status=progress oflag=sync
```

Rufus, Etcher, and Ventoy also work (the ISO carries a `loopback.cfg`).

## What the installer does on the target

Boot the machine from the stick (UEFI or legacy BIOS both work) and it lands
straight in `foundation-install` on tty1 (tty2+ are rescue shells):

1. **Hardware profile** — default is *none*: the generic core, right for mini
   PCs and anything else that boots Linux to a text console.
2. **Target disk** — picked from a menu (the live USB itself is never
   offered). The wipe is gated behind typing `ERASE` in full; anything else
   aborts untouched.
3. **Hostname + root password** — root is only for the rescue path; leaving
   the password empty locks the account.
4. Partitions (GPT; ESP+root on UEFI, BIOS-boot+root on legacy), pacstraps
   from the embedded offline repo, copies the repo to `/opt/terminal-os`,
   runs `install/run-all.sh` inside the chroot (non-interactive:
   `FOUNDATION_ASSUME_YES=1 FOUNDATION_OFFLINE=1`), installs GRUB, reboots.

First boot lands on the Home Hub login screen; register the first account
from there (see `docs/USERS.md`).

## Layout

```
build-iso.sh          the whole pipeline (stage → embed → offline repo → mkarchiso)
profile/              archiso profile
  profiledef.sh       ISO identity, boot modes (BIOS syslinux + UEFI GRUB), file perms
  packages.x86_64     LIVE environment packages only (installer tooling)
  pacman.conf         build-time pacman config
  grub/               ISO boot menu (UEFI)
  syslinux/           ISO boot menu (BIOS) — keep entries in step with grub/
  airootfs/           overlaid onto the live image's /
    usr/local/bin/foundation-install    the installer TUI
    root/.bash_profile                  autolaunch on tty1
    etc/...                             autologin, mkinitcpio-for-lts, locale
work/, out/           build scratch + output (gitignored)
```

Package-list note: the installer's pacstrap set is `base archlinux-keyring
mkinitcpio grub efibootmgr` + `install/packages.txt` (+ selected profile's
`packages.txt`). `build-iso.sh` mirrors the same union when it populates the
offline repo — if you change one, change the other (both are marked).
