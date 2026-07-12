# Install Guide

> ⚠️ This turns a machine into a locked-down, no-shell kiosk with an overseer
> that can restrict access. **Not on a machine you need a normal shell on.**
> Do a dry read of every script first; they print what they'll do.

## The normal path: the install USB (no prerequisites)

**There is nothing to install first — no Arch, no Linux, nothing.** Arch is
baked into the installer image itself: the ISO embeds this repo plus an
offline copy of every package the OS needs, so the target machine starts
from bare metal and needs no network. The whole flow is:

1. **Write a USB stick (4 GB+) on any ordinary PC.** Use the USB creator in
   [`tools/usb-creator/`](../tools/usb-creator/README.md) — on Windows,
   double-click `FoundationUSBCreator.cmd`; on macOS/Linux,
   `sudo ./create-foundation-usb.sh`. The creator finds or downloads the
   latest release ISO itself (you do not need to pre-download it). Prefer a
   **permanent staging folder** and leave `model.gguf` / the ISO there
   between releases — wiping Downloads and re-fetching everything each time
   is the slow path. Details and the update loop:
   [`tools/usb-creator/README.md`](../tools/usb-creator/README.md)
   (“Recommended workflow”). (Rufus, Etcher, Ventoy, or `dd` work for the
   ISO alone, but they do not stage Frank's local AI.)
2. **Boot the target machine from the stick** (boot-menu key at power-on:
   usually F12, F11, Esc, F2, or Del) and follow the on-screen installer:
   profile choice, disk selection (fresh install wipe is gated behind typing
   `ERASE`; an existing install offers **UPDATE** gated behind `UPDATE`),
   hostname/root password on first install — then it installs offline and
   reboots into the Home Hub.
3. **Later updates:** same stick/creator for package/ISO changes; for
   Hub/Frank/code-only releases with ethernet, prefer Settings → SYSTEM
   UPDATE (small payload) — see [`UPDATE-SYSTEM.md`](UPDATE-SYSTEM.md).
   Rebuild the stick with `-NoModel` / `FOUNDATION_NO_MODEL=1` when the mini
   PC already has Frank's AI and you only need a faster ISO write.

The rest of this guide is the **manual path** for developers, and it's also
precisely what the ISO's installer executes inside the target chroot
(`FOUNDATION_ASSUME_YES=1 FOUNDATION_OFFLINE=1 install/run-all.sh`), so
everything below — Frank isolation checks §4 included — applies to both.

## 0. Manual-path prerequisites (developers only)

> Skip this whole numbered guide if you're using the install USB above — the
> ISO satisfies all of it automatically. This path exists for iterating on
> the OS from a shell.

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

## 2. Local AI only — no cloud keys for the Assistant (spec §6, AI Chat §5)

The Hub Assistant is **local only**. It talks only to `frank-ai.service` on
`127.0.0.1:8080` (same BitNet / `llama-server` stack Frank's sensor uses).
There is **no** Mistral (or other) cloud fallback for chat — if the local
server is down, the Assistant shows an offline notice and stays offline.

Nothing secret is required for the default path. Optional technician surfaces:

- **Frank's key** (optional / legacy) — `/etc/frank/secrets.env`, owner
  `root:frank`, mode `0640`. The operator account cannot read this. Only needed
  if you deliberately turn on cloud sift/overseer/commentary
  (`backend = "cloud"` or `ai_enabled`); the **shipped default** is local
  BitNet and needs no key. Prefer leaving this empty.
  ```sh
  sudo install -o root -g frank -m 0640 /dev/null /etc/frank/secrets.env
  # optional legacy only — not used by the Hub Assistant:
  # echo 'MISTRAL_API_KEY=sk-...' | sudo tee /etc/frank/secrets.env >/dev/null
  ```
- **AI Chat's config** — `/etc/foundationhub/aichat.env`, readable by the
  operator. Defaults point at the local model; overrides stay on-box:
  ```sh
  sudo install -o root -g operator -m 0640 /dev/null /etc/foundationhub/aichat.env
  # optional technician override of URL/model (defaults are the local BitNet):
  # FOUNDATIONHUB_AI_URL=http://127.0.0.1:8080/v1/chat/completions
  # FOUNDATIONHUB_AI_MODEL=bitnet-b1.58-2B-4T
  ```

**Full offline Assistant (fresh install):** write the USB with the default
creator path (AI staging **required** — do not pass `-NoModel`). The installer
copies model + `llama-server` onto the target and enables `frank-ai.service`.
After reboot, Hub ASSISTANT talks only to `127.0.0.1:8080` (no cloud).

**Updates:** USB UPDATE with a full-AI stick refreshes code and re-lays AI if
needed; `-NoModel` is fine only when the machine already has working local AI.
Network SYSTEM UPDATE refreshes code only and **preserves** on-disk AI.

**If AI was never staged:** the rule engine still runs, Frank uses built-in
lines, and AI Chat shows a clear offline notice. Fix by rewriting the USB
without `-NoModel` and running UPDATE or INSTALL (docs/FRANK-LOCAL-AI.md).

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
