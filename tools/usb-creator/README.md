# tools/usb-creator — make the install USB from any normal PC

This is the "program you download": it turns a blank USB stick (8 GB+) into
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
GitHub's 2 GiB release-asset limit), so after writing the ISO the creator
**downloads the model and drops it onto a small data partition (`FOUNDATIONAI`)
in the stick's free space**. The OS installer stages it from there, so a
fully-offline install already has the model — no network needed on the target.

- This is **best-effort**: if the download or the extra partition can't be
  created, the stick still boots and installs fine; the target just builds or
  fetches the model on its first online run instead.
- Skip it (write only the ISO, smaller/faster): pass `-NoModel` on Windows
  (`... -File .\Create-FoundationUSB.ps1 -NoModel`) or set `FOUNDATION_NO_MODEL=1`
  on Linux/macOS. macOS staging isn't wired yet — those installs fetch online.
- The inference server binary is staged too, so the target needs **no building
  at all** — a fully-offline install gets a working AI. The creator fetches the
  prebuilt `bitnet.cpp` `llama-server` (built by CI, attached to the release as
  `foundation-ai-llama-server-x86_64`) automatically; dropping your own
  `llama-server` next to the creator script overrides it.

## Alternatives

Any ISO flasher works on the same ISO: Rufus, balenaEtcher, Ventoy, or plain
`dd` (see [`image/README.md`](../../image/README.md)).
