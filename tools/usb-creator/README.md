# tools/usb-creator — make the install USB from any normal PC

This is the "program you download": it turns a blank USB stick (4 GB+) into
the bootable Foundation TerminalOS installer. You run it on any ordinary
computer — Windows, macOS, or Linux — and then boot the *target* machine
from the stick. Neither machine needs Arch, Linux knowledge, or anything
pre-installed: the ISO it writes carries the whole OS, offline.

Both creators are attached to every GitHub release next to the ISO, so an
end user never needs this repo at all.

## Windows (double-click)

1. Download **`FoundationUSBCreator.cmd`** and **`Create-FoundationUSB.ps1`**
   into the same folder (your Downloads folder is fine). Downloading the ISO
   too is optional — the creator fetches the latest release itself if it
   doesn't find one.
2. Plug in the USB stick.
3. Double-click `FoundationUSBCreator.cmd` and follow the prompts. It asks
   Windows for administrator rights (needed to write a raw disk), shows only
   USB sticks — internal drives are never offered — and requires typing
   `ERASE` before it touches anything.

## macOS / Linux

```sh
sudo ./create-foundation-usb.sh                # auto-finds/downloads the ISO
sudo ./create-foundation-usb.sh path/to.iso    # or point it at one
```

Same behavior: only removable/USB disks are offered, `ERASE` gate before the
write.

## Then, on the target machine

Plug the stick in, power on while tapping the boot-menu key (usually **F12,
F11, Esc, F2, or Del** — it flashes on screen), pick the USB stick, and
follow the on-screen installer. It partitions the disk (gated behind typing
`ERASE` again), installs everything from packages embedded on the stick (no
network needed), and reboots into the Home Hub.

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
- This is **best-effort**: if the download can't complete or the stick is too
  small, the stick still boots and installs fine — Frank just runs rule-based
  (AI idle) until a model is provided.
- Skip it (write only the ISO, smaller/faster): pass `-NoModel` on Windows
  (`... -File .\Create-FoundationUSB.ps1 -NoModel`) or set `FOUNDATION_NO_MODEL=1`
  on Linux/macOS.
- The server binary rides along too (the prebuilt `bitnet.cpp` `llama-server`,
  built by CI and attached to the release as `foundation-ai-llama-server-x86_64`),
  so the target needs **no building at all**. Dropping your own `llama-server`
  next to the creator script overrides the download.

## Alternatives

Any ISO flasher works on the same ISO: Rufus, balenaEtcher, Ventoy, or plain
`dd` (see [`image/README.md`](../../image/README.md)).
