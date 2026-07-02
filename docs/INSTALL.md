# Install Guide

> ⚠️ This turns a machine into a locked-down, no-shell kiosk with an overseer
> that can restrict access. **Not on a machine you need a normal shell on.**
> Do a dry read of every script first; they print what they'll do.

## The flashable installer (mini PCs, or any machine from bare metal)

You don't need a hand-done Arch base install anymore: `image/build-iso.sh`
produces a bootable **installer ISO** that embeds this repo plus an offline
copy of every package the OS needs. Flash it to USB, boot the target from it,
and the on-screen installer handles profile choice, disk selection (wipe is
gated behind typing `ERASE`), partitioning, and the entire install below —
non-interactively, offline — then reboots into the Home Hub. See
[`image/README.md`](../image/README.md). The rest of this guide is the manual
path, and it's also precisely what the ISO's installer executes inside the
target chroot (`FOUNDATION_ASSUME_YES=1 FOUNDATION_OFFLINE=1
install/run-all.sh`), so everything here — Frank isolation checks §4
included — applies to both.

## 0. Prerequisites

1. A **minimal Arch base install** already booted:
   - `pacstrap /mnt base linux-lts linux-firmware` (LTS kernel — spec §1)
   - working network, a user account you'll turn into the operator, `sudo`,
     `git`.
2. This repo cloned to the target — `/opt/terminal-os` by convention, but any
   path works: `install/04` records the real location in
   `/etc/foundationhub/install-root`, nothing assumes the conventional one.
3. Decide whether you're installing the **generic core** (any x86_64 machine)
   or building a **release for a specific device** — see
   [`PROFILES.md`](PROFILES.md). For the latter, set `HARDWARE_PROFILE=<name>`
   before running anything below (e.g. `HARDWARE_PROFILE=zenbook-duo-2024`).

## 1. Order of operations

The scripts are numbered to match the spec's build order (§11) and are
**idempotent** — safe to re-run. Run them as root (they use `sudo` internally
where needed) from the repo root:

```sh
sudo ./install/run-all.sh                              # generic core
HARDWARE_PROFILE=zenbook-duo-2024 sudo -E ./install/run-all.sh   # + a profile
```

or individually, verifying between steps (recommended for the first install):

```sh
sudo ./install/00-base-packages.sh     # package set (§1)
sudo ./install/01-kernel.sh            # pin linux-lts (§1)
sudo ./install/02-console-kiosk.sh     # kernel-VT kiosk, autologin, login shell (§2,§4)
sudo ./install/03-plymouth-grub.sh     # text plymouth + strip quiet/rhgb (§3)
sudo ./install/04-hub.sh               # install foundationhub as the login shell (§4,§5)
sudo ./install/05-frank.sh             # frank user, daemon, isolation (§6)
sudo ./install/06-theme-sound.sh       # CRT theme + soundscape (§8,§10)
sudo HARDWARE_PROFILE=zenbook-duo-2024 ./install/07-hardware-profile.sh   # optional (§7)
```

Steps 00–06 are hardware-agnostic. Step 07 is a no-op unless
`HARDWARE_PROFILE` names a directory under `profiles/`; see
[`PROFILES.md`](PROFILES.md) for what a profile can add and how to write one.

### The manual kernel gate (profile-specific)

If you're building the `zenbook-duo-2024` profile: **before going further,
verify the bottom panel (eDP-2) actually works on the installed kernel.**
Step 07 finishes by printing the check:

```sh
wlr-randr            # (from within the profile's cage session) should list eDP-1 AND eDP-2
```

(`wlr-randr` and the cage session it runs in are installed *by this profile*
— the generic core has no display stack to run it from.)

If eDP-2 is missing or glitching, the LTS point release has a known i915
regression on this device; follow the profile's printed fallback to pin a
known-good version (target 6.8.12) from the Arch Linux Archive. Do not
continue on a kernel where the second screen is broken. This gate is specific
to this one profile — the generic core has no such requirement.

## 2. Configuring API keys (spec §6, AI Chat §5)

Nothing secret is committed. Two **separate** keys (see ARCHITECTURE.md — the
two Mistral integrations are isolated):

- **Frank's key** — `/etc/frank/secrets.env`, owner `root:frank`, mode `0640`.
  The operator account cannot read this.
  ```sh
  sudo install -o root -g frank -m 0640 /dev/null /etc/frank/secrets.env
  echo 'MISTRAL_API_KEY=sk-...' | sudo tee /etc/frank/secrets.env >/dev/null
  ```
- **AI Chat's key** — `/etc/foundationhub/aichat.env`, readable by the operator.
  ```sh
  sudo install -o root -g operator -m 0640 /dev/null /etc/foundationhub/aichat.env
  echo 'MISTRAL_API_KEY=sk-...' | sudo tee /etc/foundationhub/aichat.env >/dev/null
  ```

**With no keys set (current default):** the rule engine runs fully offline,
Frank speaks with the built-in fallback lines, and AI Chat shows a clear "no key
configured" screen. Everything else works.

## 3. Making foundationhub the login shell (spec §4)

`04-hub.sh` installs `/usr/local/bin/foundationhub-session` and runs:

```sh
chsh -s /usr/local/bin/foundationhub-session operator
```

After this, the operator has **no bash shell** — logging in execs foundationhub
directly on the kernel VT (or via the hardware profile's display-stack plugin
if one is installed), and exiting foundationhub logs out. Keep a separate root
TTY or a rescue path available until you've confirmed it works (see "Recovery"
below).

## 4. Frank isolation checks (spec §6)

The operator must have **no power over Frank, ever**. After `05-frank.sh`,
confirm every one of these is DENIED (the script runs these too and aborts if
any succeeds):

```sh
sudo -u operator cat /etc/frank/config.toml        # Permission denied
sudo -u operator cat /var/lib/frank/incidents.db   # Permission denied
sudo -u operator cat /var/lib/frank/lockout.state  # Permission denied
sudo -u operator systemctl stop frankd             # fails (no polkit/sudo path)
sudo -u operator systemctl stop frank-enforcer     # fails
```

There is also no operator-facing way to *tune* Frank: the Hub↔Frank socket is
read-only (the Hub can only receive warnings to display), there is no sensitivity
setting in the Hub, and there is no `set_*` IPC command anywhere. If any check
above succeeds, isolation is broken — see ARCHITECTURE.md → "Frank isolation."

## Recovery / safety while building

Until the system is proven:

- Add a **second getty on tty2 with a normal root shell** you can Ctrl-Alt-F2
  to. Remove it only once you trust the kiosk.
- Keep an Arch live USB handy. Reverting the login shell is
  `chsh -s /bin/bash operator` from any root shell.
- `install/uninstall.sh` reverses the login-shell change, disables the kiosk
  autologin, and stops/masks `frankd` (run as root from a rescue shell).

## Uninstall

```sh
sudo ./install/uninstall.sh
```

Restores the operator's shell to `/bin/bash`, disables autologin + kiosk, and
stops Frank. It intentionally leaves `/var/lib/frank` in place (incident data)
unless you pass `--purge`.
