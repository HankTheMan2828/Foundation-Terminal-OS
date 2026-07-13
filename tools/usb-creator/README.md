# tools/usb-creator — make the install USB from any normal PC

This is the "program you download": it turns a blank USB stick (4 GB+) into
the bootable Foundation TerminalOS installer. You run it on any ordinary
computer — Windows, macOS, or Linux — and then boot the *target* machine
from the stick. Neither machine needs Arch, Linux knowledge, or anything
pre-installed: the ISO it writes carries the whole OS, offline.

Both creators are attached to every GitHub release next to the ISO, so an
end user never needs this repo at all.

## Recommended workflow (repeat installs / updates)

**Do not** delete Downloads and re-download everything each release. That
path double-fetches the ISO (~1.5 GB) and often re-downloads the AI model
(~1.2 GB). Use a permanent staging folder instead.

### One-time setup (Windows)

1. Create a permanent folder, e.g. `C:\Users\<you>\Foundation-USB-Cache\`.
2. Put **`FoundationUSBCreator.cmd`** and **`Create-FoundationUSB.ps1`** in
   that folder (from a release, or copy from this directory).
3. Leave the folder alone between releases. After the first successful run it
   will also hold:
   - `foundation-terminalos-*.iso` — installer (refreshed when outdated)
   - `model.gguf` — Frank AI weights (keep forever)
   - `ai-runtime.tar.gz` — llama-server **+ libllama/libggml** (keep forever;
     a bare `llama-server` ELF alone will **not** start on the target)
   After a successful write the creator **verifies** the AI sidecar
   (`FOUNDATIONAI2` header + GGUF + gzip magic). If you do not see
   `AI sidecar verified`, do not use that stick for a first AI install.

### Every new version

1. Plug in the USB stick.
2. Double-click `FoundationUSBCreator.cmd` **from that cache folder**.
3. The creator:
   - reuses a local ISO if it matches the current GitHub release (SHA checked);
   - downloads a **new** ISO only when yours is missing or stale;
   - reuses `model.gguf` / `ai-runtime.tar.gz` once they exist (no re-download);
   - **probes the stick** and picks the cheapest safe write mode (below).
4. On the mini PC: boot the stick → **UPDATE** → type `UPDATE`  
   (use **INSTALL** / `ERASE` only for a full wipe).

### Stick-aware write modes (automatic)

Before writing, the creator compares the stick to the local ISO and AI files:

| Stick state | Mode | Confirm word | What happens |
|---|---|---|---|
| ISO + AI already match | **skip** | — | Nothing written |
| ISO matches, AI missing/stale | **ai_only** | `STAGE` | Write AI sidecar only (~1.2 GB) |
| ISO stale, AI still good | **iso_only** | `UPDATE` | Rewrite ISO only; keep AI past 2 GiB |
| Blank / both need update | **full** | `ERASE` | `diskpart clean` + ISO + AI |

Force a full wipe anytime:

```powershell
powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -ForceFull
```

```sh
FOUNDATION_FORCE_FULL=1 sudo ./create-foundation-usb.sh
```

### Faster write when the mini PC already has Frank AI

Skip re-staging the ~1.2 GB model onto the stick:

```powershell
powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -NoModel
```

With `-NoModel`, probe still applies: matching ISO → skip; stale ISO →
ISO-only rewrite (no AI touch).

Use full staging (default, no `-NoModel`) for a **first install** or when the
target has no working local AI yet.

### Fix "idle: missing: runtime model" without re-imaging the ISO

The main creator now chooses **ai_only** automatically when the ISO matches
but the AI sidecar is missing. You can still run the dedicated helper:

```powershell
powershell -ExecutionPolicy Bypass -File .\Stage-FoundationAI.ps1
```

Confirm it prints `AI sidecar verified`, then boot the mini PC → **UPDATE**.

### Even faster: no USB (code-only updates)

If the mini PC has ethernet and transport policy allows it
(`usb+wired` is the default), use **Settings → SYSTEM UPDATE** instead.
That applies the small `terminalos-payload-*.tar.gz` (~1 MB). Base package
upgrades still need the USB path — see [`docs/UPDATE-SYSTEM.md`](../../docs/UPDATE-SYSTEM.md).

### What not to do

| Slow habit | Better |
|---|---|
| Delete all TerminalOS files from Downloads each time | Keep a permanent cache folder |
| Manually download the ISO, then run the creator (it may download again) | Let the creator fetch/refresh the ISO |
| Re-download the AI model every release | Keep `model.gguf` next to the scripts |
| Full AI staging for every stick refresh | Let probe pick `iso_only` / `skip`, or `-NoModel` |
| Force-rewriting an already-current stick | Run again — probe should **skip** |
| USB for every Hub/Frank code change | Settings → SYSTEM UPDATE when possible |

---

## Windows (double-click) — first-time / end user

1. Download **`FoundationUSBCreator.cmd`** and **`Create-FoundationUSB.ps1`**
   into the same folder (a permanent folder is better than Downloads — see
   above). Downloading the ISO too is optional — the creator fetches the
   latest release itself if it doesn't find one.
2. Plug in the USB stick.
3. Double-click `FoundationUSBCreator.cmd` and follow the prompts. It asks
   Windows for administrator rights (needed to write a raw disk), shows only
   USB sticks — internal drives are never offered — probes what is already
   on the stick, and gates the write with `ERASE` / `UPDATE` / `STAGE`
   depending on mode.

Point at a specific ISO (skip discovery):

```powershell
powershell -ExecutionPolicy Bypass -File .\Create-FoundationUSB.ps1 -Iso C:\path\to\foundation-terminalos-....iso
```

## macOS / Linux

```sh
sudo ./create-foundation-usb.sh                # auto-finds/downloads the ISO
sudo ./create-foundation-usb.sh path/to.iso    # or point it at one
FOUNDATION_NO_MODEL=1 sudo ./create-foundation-usb.sh   # never stage AI
FOUNDATION_FORCE_FULL=1 sudo ./create-foundation-usb.sh # always full wipe
```

Same stick-aware modes as Windows: only removable/USB disks are offered;
confirm with `ERASE` / `UPDATE` / `STAGE` as prompted. Keep `model.gguf` and
`ai-runtime.tar.gz` next to the script so later runs do not re-download them.

## Then, on the target machine

Plug the stick in, power on while tapping the boot-menu key (usually **F12,
F11, Esc, F2, or Del** — it flashes on screen), pick the USB stick, and
follow the on-screen installer:

- **Existing install** → choose **UPDATE**, confirm with `UPDATE` (preserves
  accounts, home data, and Frank state).
- **Bare machine / wipe** → **INSTALL**, confirm with `ERASE`.

It installs from packages embedded on the stick (no network needed) and
reboots into the Home Hub.

> ⚠️ The installed system is a locked-down, no-shell kiosk with an always-on
> overseer (Frank). Don't point it at a machine you still need as a normal PC.

## Frank's local AI model (staged onto the stick)

The installed OS runs a small **local** AI model for its overseer (Frank) —
BitNet b1.58 2B4T, ~1.2 GB. That's too big to bake into the ISO (it would blow
GitHub's 2 GiB release-asset limit), and the target mini PCs have **no network**,
so the model must ride on the stick. The creator downloads the model + the AI
server binary and writes them, as a **raw-offset sidecar**, into the stick's free
space *past the ISO* (a fixed 2 GiB offset — just past a sub-2 GB ISO, so the AI
plus a 2 GiB image fits a 3.8 GB stick). The OS installer reads them straight
off the raw device — so a fully-offline install already has a working AI, with no
building on the target.

- **Why raw bytes, not a data partition?** Windows won't surface a volume for a
  second partition on a removable stick that was raw-written with an ISO (both the
  Storage cmdlets and diskpart fail). Writing raw bytes past the ISO sidesteps
  that entirely and can't affect bootability.
- **Required by default:** if the model or server binary cannot be prepared, the
  creator **aborts before writing** so you never ship a "fresh install" stick
  with a dead Assistant. Fix the download / stick size, then re-run.
- Skip AI only when the target **already** has working local AI (faster refresh):
  pass `-NoModel` on Windows (`... -File .\Create-FoundationUSB.ps1 -NoModel`)
  or set `FOUNDATION_NO_MODEL=1` on Linux/macOS.
- The server binary rides along too (the prebuilt `bitnet.cpp` `llama-server`,
  built by CI and attached to the release as `foundation-ai-llama-server-x86_64`),
  so the target needs **no building at all**. Dropping your own `llama-server`
  next to the creator script overrides the download.

## Alternatives

Any ISO flasher works on the same ISO: Rufus, balenaEtcher, Ventoy, or plain
`dd` (see [`image/README.md`](../../image/README.md)). Note: third-party
flashers do **not** stage Frank's local AI sidecar — use this creator when the
target needs offline AI on first boot.
