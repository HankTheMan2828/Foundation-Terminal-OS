# Install Guide

> ⚠️ This turns a machine into a locked-down, no-shell kiosk with an overseer
> that can restrict access. **Install on the target Zenbook Duo, not on a
> machine you need a normal shell on.** Do a dry read of every script first;
> they print what they'll do.

## 0. Prerequisites

1. A **minimal Arch base install** already booted on the UX8406MA:
   - `pacstrap /mnt base linux-lts linux-firmware` (LTS kernel — spec §1)
   - working network, a user account you'll turn into the operator, `sudo`,
     `git`.
2. This repo cloned to the target, e.g. `/opt/zenbook-terminal-os`.

## 1. Order of operations

The scripts are numbered to match the spec's build order (§11) and are
**idempotent** — safe to re-run. Run them as root (they use `sudo` internally
where needed) from the repo root:

```sh
sudo ./install/run-all.sh
```

or individually, verifying between steps (recommended for the first install):

```sh
sudo ./install/00-base-packages.sh     # package set (§1)
sudo ./install/01-kernel-lts.sh        # pin linux-lts; SECOND-SCREEN CHECK (§1,§11.2)
sudo ./install/02-cage-kiosk.sh        # cage+kitty kiosk, autologin, login shell (§2,§4)
sudo ./install/03-plymouth-grub.sh     # text plymouth + strip quiet/rhgb (§3)
sudo ./install/04-hardware-zenbook.sh  # Duo display/brightness/battery/detach (§7)
sudo ./install/05-polkit-backlight.sh  # replace NOPASSWD sudo hole (§7)
sudo ./install/06-hub.sh               # install zenhub as the login shell (§4,§5)
sudo ./install/07-frank.sh             # frank user, daemon, isolation (§6)
sudo ./install/08-theme-sound.sh       # CRT theme + soundscape (§8,§10)
```

### The critical manual gate: step 1 / §11.2

**Before going further, verify the bottom panel (eDP-2) actually works on the
installed kernel.** `01-kernel-lts.sh` finishes by printing the check:

```sh
wlr-randr            # (from within a cage session) should list eDP-1 AND eDP-2
```

If eDP-2 is missing or glitching, the LTS point release has the i915
regression; follow the script's printed fallback to pin a known-good version
(target 6.8.12) from the Arch Linux Archive. Do not build the rest on a kernel
where the second screen is broken.

## 2. Configuring API keys (spec §6, AI Chat §5)

Nothing secret is committed. Two **separate** keys (see ARCHITECTURE.md — the
two Mistral integrations are isolated):

- **Frank's key** — `/etc/frank/secrets.env`, owner `root:frank`, mode `0640`.
  The operator account cannot read this.
  ```sh
  sudo install -o root -g frank -m 0640 /dev/null /etc/frank/secrets.env
  echo 'MISTRAL_API_KEY=sk-...' | sudo tee /etc/frank/secrets.env >/dev/null
  ```
- **AI Chat's key** — `/etc/zenhub/aichat.env`, readable by the operator.
  ```sh
  sudo install -o root -g operator -m 0640 /dev/null /etc/zenhub/aichat.env
  echo 'MISTRAL_API_KEY=sk-...' | sudo tee /etc/zenhub/aichat.env >/dev/null
  ```

**With no keys set (current default):** the rule engine runs fully offline,
Frank speaks with the built-in fallback lines, and AI Chat shows a clear "no key
configured" screen. Everything else works.

## 3. Making zenhub the login shell (spec §4)

`06-hub.sh` installs `/usr/local/bin/zenhub-session` and runs:

```sh
chsh -s /usr/local/bin/zenhub-session operator
```

After this, the operator has **no bash shell** — logging in execs
cage→kitty→zenhub, and exiting zenhub logs out. Keep a separate root TTY or a
rescue path available until you've confirmed it works (see "Recovery" below).

## 4. Frank isolation checks (spec §6)

The operator must have **no power over Frank, ever**. After `07-frank.sh`,
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
