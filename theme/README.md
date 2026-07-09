# Theme — CRT phosphor look (spec §2, §8)

One fixed look: **base yellow on near-black**, scanlines, glow, monospace bitmap
font (Terminus). No palette switcher — the OS has a single hue everywhere, the
same yellow the installer and login screens use.

Two layers combine for the look:

1. **The kernel console itself** (`system/usr/local/bin/foundationhub-session`)
   — sets the bitmap console font (`setfont ter-v16b`, Terminus) and retunes
   the VT's yellow slot (console index 3, stock brown `#aa5500`) to base yellow
   `#ffff55` via the kernel's `\e]PXRRGGBB` escape. This is a plain
   Linux-console feature: no compositor, no graphical terminal, no GPU.
2. **The TUI itself** (`hub/foundationhub/theme.py`) — draws the frame/bezel, the
   scanline dimming on alternate rows, and the "glow" via inverse highlight on
   the selected row. It renders in `COLOR_YELLOW`, which the session script has
   retuned to the base-yellow hue on the VT.

The kitty palette config (`kitty.conf`) lives under
`profiles/zenbook-duo-2024/system/etc/foundationhub/` — it only exists for that
profile's display-stack plugin; the core has no kitty.

Deferred to the dedicated visual pass (spec §11.10): bloom/glow and a true
scanline overlay. On the bare VT the options are character-level effects only
— anything shader-based would belong to a profile's display stack, never the
core. Not in v1.
