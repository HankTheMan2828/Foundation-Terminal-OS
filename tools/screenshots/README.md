# Preview screenshots — TEMPORARY dev tooling

> ⚠️ **This directory is not part of the OS.** It's a throwaway preview harness
> so you can *see* the Home Hub and Frank's surfaces without a Zenbook — handy
> while this is being built off-device. **Delete `tools/screenshots/` once the
> system is running on real hardware** (real screenshots from the device will
> be truer than these approximations).

## What you're looking at

The PNGs in [`preview/`](preview/) are captured from the **actual running code**
— not mockups. The harness runs `python -m foundationhub` (and the real `frank-locker`)
inside a pseudo-terminal, reads back the terminal's character grid with `pyte`,
and renders it with an amber-phosphor style (scanlines, glow, highlight bar).

Start with [`preview/00_contact_sheet.png`](preview/00_contact_sheet.png) for
the overview; the numbered PNGs are the full-res individual screens.

### Honest caveats
- The CRT styling (amber, scanlines, glow) is applied by the **renderer**, not
  the terminal. On the real device the look comes from kitty's config + the
  TUI's own drawing; the *content* here is authentic, the exact glow/font
  (DejaVu Sans Mono here vs. Terminus on device) will differ.
- Box-drawing borders are redrawn by the renderer (pyte returns raw VT100
  charset codes); on real kitty they'll be proper Unicode box lines.
- Colors are the 8-color approximation; true amber (#FFB000) needs a terminal
  that can redefine its palette (the target kitty config does).

## Regenerate

Needs `pyte` and `pillow` (dev-only; not runtime deps of the OS):

```sh
pip install pyte pillow
cd tools/screenshots
python3 capture_hub.py        # 01..11 Home Hub screens
python3 capture_frank.py      # 12 lockout, 13 populated ledger
python3 contact_sheet.py      # 00 overview montage
```

Output lands in `preview/`. Everything is repo-relative, so it runs from a
fresh clone with no device.

## Files
```
_render.py        shared CRT renderer (grid -> PNG)
_pty.py           pty driver: run app, feed vim keys, snapshot the grid
capture_hub.py    drives foundationhub through all Home Hub areas
capture_frank.py  frank-locker lockout + a populated (seeded) Overseer Ledger
contact_sheet.py  stitches preview/*.png into 00_contact_sheet.png
preview/          the committed PNGs (so you can see them without running)
```
