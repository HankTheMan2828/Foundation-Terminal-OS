# Update System — Design + implementation notes

> Status: 🟨 **BUILT 2026-07-04** (operator approved implementing same-day,
> with the §12 recommended defaults). Source ask:
> `docs/FEEDBACK-FIRST-HARDWARE-RUN.md` item 11. The remaining
> [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) §12 items (signing, and any
> default the operator wants changed) stay open — the code implements the
> recommendations and marks where each pending decision slots in. Not yet
> exercised on hardware (§8 step 7).

An installed Foundation TerminalOS machine needs a way to update: **via USB
or over the network**, with the allowed transports being a **per-machine
policy setting** (a company deployment restricts to USB or hardwired
ethernet; wireless exists but only as an opt-in configured from Settings).

## 1. Design principles

1. **No persistent update daemon — ever.** (DOS-grade minimalism.) Nothing
   polls, nothing auto-checks, no timer units. An update happens only when a
   person initiates one: by booting the release USB, or by opening
   Settings → SYSTEM UPDATE and asking. The only new unit is a `Type=oneshot`
   service that is *started on demand and exits* — the same shape as running
   a program, not a daemon.
2. **The release ISO is the update medium.** Zero new offline artifacts: the
   ISO already embeds the full repo + the tested offline package repo, and
   the USB creator already exists. USB update = the same stick a company
   would use to install.
3. **Updates preserve people's stuff.** `/home`, the account registry, all
   per-user data trees, machine-wide scores, and **all Frank state** survive
   an update. An update refreshes the OS payload; it is not a reinstall.
4. **No update path may weaken Frank isolation.** Hard rule, detailed in §6.
   This includes the subtle case: an update must not *clear an active
   lockout* and must not hand the operator any new privileged path.
5. **Transport policy is enforced, not advisory.** The network path checks
   the policy before touching the network, and refuses (with an honest
   message) rather than degrading.

## 2. Version identity (prerequisite for both paths)

Release tags follow **semver** `vMAJOR.MINOR.PATCH` — first stable line is
**`v0.1.x`**. Full scheme: [`VERSIONING.md`](VERSIONING.md). Both update
paths need "what am I running" vs. "what is available":

- `image/build-iso.sh` writes a `VERSION` file into the embedded repo copy
  at build time, containing `git describe --tags --always` (in CI on a tag
  build this is exactly `v0.1.0`) plus the build date.
- `install/10-update-system.sh` records **`/etc/foundation-release`** on the
  target: version, build date, the hardware profile applied (so an update
  never has to re-ask), and an append-only history line per install/update
  (`installed 2026-07-13 v0.1.0`, `updated 2026-07-20 v0.1.1`, …).
- A dev-tree install without `VERSION` records `dev-<git describe>` or
  `unversioned` — honest, never faked.
- Settings → SYSTEM STATUS shows a read-only VERSION line from this file.
- **Legacy installs** still carry `TerminalOS-v0.0.N` in
  `/etc/foundation-release`; compare is numeric on the triple, so
  `v0.1.0` is correctly offered over `TerminalOS-v0.0.24`.

## 3. Transport policy (per-machine setting)

One root-owned file, **`/etc/foundation-update.conf`**, read at the moment
an update is attempted (never watched):

```
# allowed transports for system updates (one of)
#   usb            — offline only: updates arrive on the release USB stick
#   usb+wired      — USB, or network updates over ethernet only
#   usb+wired+wireless — wireless additionally allowed (opt-in)
transports = usb+wired
```

- **Default: `usb+wired`** — matches the company posture (USB or hardwire),
  wireless off until someone opts in.
- **Enforcement, not decoration:** before any network fetch, the update
  runner checks the default route's interface class (wired vs `wlan*`) and
  refuses on a wireless route unless policy allows it. When policy excludes
  wireless, the WiFi radio is kept off at the NetworkManager level
  (`nmcli radio wifi off`, persisted), so "wired only" is a machine state,
  not a request.
- **Settings surface:** Settings gains an UPDATE POLICY line showing the
  current mode. Enabling wireless is done here (the operator ask: "wireless
  as an opt-in from the Settings area") — flipping to `usb+wired+wireless`
  re-enables the radio and makes NETWORK (`nmtui`) able to join WiFi.
  *Who* is allowed to flip it is a trust question → OPEN-QUESTIONS §12
  (recommendation: TECHNICIAN tier, setup-code gated, written through a
  root helper in the `foundationhub-account` pattern — the file itself stays
  root-owned, never operator-writable).
- When policy is `usb`, the SYSTEM UPDATE screen still exists but says so:
  "updates arrive by USB on this machine" — no dead buttons.

## 4. Path A — USB update (UPDATE mode in `foundation-install`)

Reuses the installer medium end to end. `foundation-install` grows a mode
selection right after its banner:

**Detection.** Scan candidate disks (live medium still excluded) for an
ext4 partition labeled `foundation-root`; probe-mount read-only and confirm
it is really ours (`/opt/terminal-os/install/run-all.sh` +
`/etc/foundation-release` present). If found, the menu offers:

```
  1) UPDATE the existing Foundation TerminalOS on /dev/sda2
       currently: v0.1.0   this medium: v0.1.1
  2) INSTALL fresh (ERASES a disk completely)
```

No existing install found → straight to the current install flow, unchanged.

**Confirmation.** UPDATE is non-destructive but still system-surgery: it is
confirmed by typing `UPDATE` in full (deliberately a different word than
`ERASE` — muscle memory for one can never trigger the other). Same-version
medium → say so and require an explicit "reapply anyway" choice (useful for
repairing a damaged install).

**Flow** (contrast with install: no partitioning, no mkfs, no identity
questions):

1. Mount the root partition (and its ESP on UEFI) at `/mnt` — read-write,
   nothing formatted.
2. **Package upgrade from the embedded offline repo:** the same
   `foundation-pacstrap.conf` mechanism install uses, but
   `pacman -Syu --sysroot` / chroot'd `pacman -Syu` against
   `file:///opt/foundation/pkgs` — the machine moves to the exact package
   set this release was tested with, no network involved. Packages newly
   added to `install/packages.txt` since the installed version are installed
   too (delta of the list).
3. **Refresh the OS payload:** replace `/opt/terminal-os` on the target with
   the medium's repo tree (it is OS code, not user data — nothing of the
   user's lives there), restore exec bits (same mkarchiso quirk the
   installer already handles).
4. **Re-run `install/run-all.sh` in the chroot** with
   `FOUNDATION_ASSUME_YES=1 FOUNDATION_OFFLINE=1` and a new
   **`FOUNDATION_UPDATE=1`**, plus the hardware profile read back from
   `/etc/foundation-release` (never re-asked). The steps are already
   written to be idempotent; `FOUNDATION_UPDATE=1` additionally means
   **"no-clobber for state"** — see the preservation contract below and the
   required fixes in §4.1.
5. `grub-mkconfig` re-run; `grub-install` re-run best-effort (a kernel or
   GRUB package bump makes this necessary; it is harmless otherwise).
6. Frank **isolation checks re-run** (they already live at the end of
   `install/05-frank.sh`) — a failure fails the update loudly.
7. Stamp `/etc/foundation-release` (new version + `updated` history line),
   copy the update log next to the install log, unmount, reboot.

**Preservation contract** (the table an operator can hold us to):

| On the target | Update treatment |
|---|---|
| `/home/**` (accounts' files, notes, media) | untouched |
| `/etc/foundationhub/users.json` (account registry) | untouched (install/04 is already no-clobber) |
| `/etc/foundationhub/console-font`, theme choice | untouched — Settings choices survive |
| `/var/lib/foundationhub/` (machine-wide scores, chess) | untouched |
| `/var/lib/frank/**` (incidents, ledgers, **lockout.state**) | untouched — see §4.1 |
| `/etc/frank/config.toml` (root-tuned: sensitivity etc.) | preserved; new defaults land beside it as `config.toml.new` for root to merge |
| `/etc/frank/secrets.env`, rules.d | secrets preserved (already no-clobber); rules.d refreshed (shipped content, root:frank perms re-asserted) |
| `/opt/terminal-os` (OS payload) | replaced |
| Hub/Frank/games/media code, units, bins | replaced (that's the update) |
| Arch packages | upgraded to the release's tested offline-repo set |

### 4.1 Required fixes for a safe re-run (found while designing)

- **`install/05-frank.sh:37` truncates `/var/lib/frank/lockout.state` on
  every run** (`install … /dev/null lockout.state` has no `[[ -e ]]` guard
  the way `secrets.env` and `users.json` do). Today that means re-running
  install steps **clears an active machine lockout** — a USB update would be
  a lockout-escape path. Fix: guard it like `secrets.env`. This is the
  concrete instance of the §6 hard rule: **an active lockout survives an
  update; the enforcer re-arms it on the post-update boot** exactly as it
  re-arms after any reboot (that machinery already exists).
- `install/05-frank.sh:24` unconditionally overwrites `/etc/frank/config.toml`
  — would silently reset a root-tuned sensitivity/thresholds. Fix: under
  `FOUNDATION_UPDATE=1`, preserve and drop `config.toml.new` beside it.
- `install/02` must not clobber `/etc/foundationhub/console-font` when it
  exists (text-size choice survives; `FOUNDATION_CONSOLE_FONT` seeding is
  install-time only).
- Sweep the other steps for the same shape (anything `install`-ing over a
  state file) as part of implementation; the *code* refresh parts stay
  unconditional.

## 5. Path B — network update (Settings → SYSTEM UPDATE)

A new Settings entry, **SYSTEM UPDATE**, in the Hub. Everything is
on-demand; nothing checks in the background.

**Check.** One HTTPS GET to the GitHub releases API
(`/repos/HankTheMan2828/Foundation-Terminal-OS/releases/latest`, stdlib
`urllib`, no new dependencies), gated by transport policy *before* the
socket opens. Screen shows: current version (from `/etc/foundation-release`),
latest release tag, and either "up to date" or an APPLY item.

**What is downloaded — recommendation: the OS payload, not the ISO.** The
release gains one small CI artifact, `terminalos-payload-<ver>.tar.gz` — the
same repo tree the ISO embeds (a few MB), plus its SHA256 and (pending the
§12 signing decision) a detached signature. The network path updates the OS
payload (Hub, Frank, games, media, install scripts, units) and re-runs the
install steps with `FOUNDATION_UPDATE=1`. **Arch base-package upgrades stay
on the USB path in v1**: the offline repo *is* the tested package set;
pulling rolling Arch mirrors over the network would move machines onto
package versions no release was built against, and would make update size
~GB instead of ~MB. Consequence to be explicit about: a release whose
changes require new/upgraded packages says so in its notes and needs the
USB path — the payload manifest carries a `requires-usb: yes/no` flag so
the SYSTEM UPDATE screen can tell the operator honestly instead of applying
half an update. (Routed to §12 as a scoping decision.)

**How it applies without a daemon and without giving the operator root.**
The operator account has no root and must not gain any general privilege.
Mechanism (as built — the repo already had exactly this shape in
`foundationhub-account`, so the update helper reuses the proven pattern
instead of a systemd oneshot + unit-scoped polkit):

- A root-owned helper **`/usr/local/bin/foundation-update`** (fixed logic:
  `apply` and `set-policy <mode>` only), reached from the Hub via **pkexec**
  under a polkit rule scoped to exactly that program
  (`50-foundation-update.rules`) — nothing persistent, it runs and exits.
- The helper is the authoritative gate, not the Hub: it re-reads the
  transport policy against the live route, **verifies the technician setup
  code against the root-owned registry on stdin**, and verifies the payload
  checksum (staging dir `/var/lib/foundation-update/`, root-owned 0700)
  before anything is touched. Signature verification (§12) slots into its
  `_verify()`.
- Applies the same sequence as the USB path steps 3–7 (payload refresh →
  `run-all.sh` with `FOUNDATION_UPDATE=1` + `FOUNDATION_OFFLINE=1` so
  nothing shops mirrors → isolation checks → stamp release file); the Hub
  then tells the operator to restart from the POWER menu.
- **Who may start it**: implemented as the §12 recommendation — TECHNICIAN
  tier in the Hub *plus* setup-code re-entry (the helper re-verifies the
  code, so the pkexec grant alone is not enough). The stricter §12
  alternative (notify-only, USB-applies) remains available by decision.

**Failure honesty.** Wrong checksum/signature → staged files deleted, clear
message, nothing applied. Download interrupted → nothing applied (staging is
not the live system). Isolation check fails post-apply → the update is
declared failed on screen and in the log; the machine is left bootable (the
payload swap is directory-replace, old payload kept at
`/opt/terminal-os.prev` until the new one passes checks).

## 6. Hard rule: updates must never weaken Frank isolation

For §12 sign-off, stated as testable invariants:

1. **No new operator→root path**, except (pending approval) the single
   polkit rule scoped to starting `foundation-update.service` — which runs
   fixed root-owned logic the operator cannot influence (no args, no
   operator-writable inputs; the payload it applies is checksum/signature
   verified). If that exception is declined in §12, there is zero.
2. **Frank state is never reset by an update**: `/var/lib/frank/**`
   untouched, `lockout.state` never truncated (§4.1 fix), **active lockouts
   survive and re-arm after the post-update reboot**.
3. **Frank config ownership/permissions are re-asserted, never loosened**
   (`root:frank 0750/0640` re-applied by the same install steps); root-local
   tuning preserved (§4.1).
4. **The isolation check suite runs at the end of every update** (both
   paths) and a failure fails the update — same checks, same "all must be
   DENIED" bar as first install.
5. **The update system gives the operator no read/write window into Frank's
   files** at any point: staging dirs are root/`update`-owned; logs shown to
   the operator contain versions and step names, not Frank data.
6. USB physical access remains out of scope per spec §6 (a USB boot could
   always do anything); the rule here is that our *sanctioned* update flows
   preserve isolation — including honoring lockouts — rather than providing
   a polite bypass.

## 7. Non-goals (v1)

- No auto-update, no scheduled checks, no background anything.
- No delta/binary-diff packages; payload replace is the mechanism.
- No downgrade flow (reinstall via ERASE covers rollback; `.prev` payload
  is crash-safety, not a feature).
- Wireless *provisioning* stays on `nmtui` (Settings → NETWORK → CONFIGURE);
  that screen also has link status + WiFi radio for everyday use (Web Access).
  The update-policy toggle still governs whether *updates* may use wireless.
- Base-package upgrades over the network (USB path owns those in v1 — §5).

## 8. Implementation plan — status (built 2026-07-04)

1. ✅ Version identity: `VERSION` stamped by `image/build-iso.sh` (and by CI
   into the payload); `/etc/foundation-release` written by the new
   `install/10-update-system.sh`; VERSION shown in SYSTEM STATUS and on the
   Settings SYSTEM UPDATE row.
2. ✅ No-clobber fixes (§4.1): `lockout.state` guarded (never truncated),
   `/etc/frank/config.toml` preserved with `.new` beside it under update,
   console-font preserved; `is_update()` helper in `install/common.sh`.
3. ✅ UPDATE mode in `foundation-install`: detection (probe-mount of
   `foundation-root`-labeled partitions), UPDATE/INSTALL menu, typed
   `UPDATE` confirm, offline `pacman -Syu` via bind-mounted embedded repo,
   payload swap with `.prev`, `run-all.sh` in update mode, best-effort
   GRUB, update log.
4. ✅ Transport policy: `system/etc/foundation-update.conf` (default
   `usb+wired`, no-clobber on update), enforced in both the Hub pre-check
   (`hub/foundationhub/updates.py`) and the root helper; policy changes
   flip the WiFi radio via nmcli.
5. ✅ CI payload: `terminalos-payload-<tag>.tar.gz` + SHA256SUMS line,
   attached to releases by `build-iso.yml`. Signature: pending §12.
6. ✅ `foundation-update` root helper (pkexec, scoped polkit rule — see §5)
   + Settings → SYSTEM UPDATE screen (`screens/updates.py`): on-demand
   CHECK, technician-gated APPLY and UPDATE POLICY. Backend unit-tested
   (`hub/tests/test_updates.py`).
7. ⬜ **Hardware pass — the remaining step:** run a real `v0.1.x` →
   `v0.1.y` (or legacy `TerminalOS-v0.0.x` → `v0.1.0`) USB update on the
   mini PC testbed; verify the preservation contract table row by row;
   verify an active lockout survives; exercise the network path
   end-to-end against a real release.

Each landed on `Terminal-OS-Main` directly, per the single-mainline policy.
