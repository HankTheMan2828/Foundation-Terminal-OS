# Theme — CRT phosphor look (spec §2, §8)

One fixed look: **base yellow on near-black**, scanlines, glow, monospace bitmap
font (Terminus). No palette switcher — the body is a single hue everywhere, the
same yellow the installer and login screens use.

On top of the base yellow sit a few **warm accent slots**, retuned the same way
(VT `\e]PXRRGGBB` + the kitty profile), so bold text stays on-hue:

| Slot (idx / bright) | Color   | Used for |
|---------------------|---------|----------|
| base — 3            | `#ffff55` yellow | body text, frame |
| amber — 2 / 10      | `#f59f00` amber | **top banner text + bottom nav line**; games' "dark" side |
| cream — 7 / 15      | `#fff0c0` cream white | games: chess light pieces, hot 2048 tiles |
| teal — 6 / 14       | `#7fdfe0` soft teal | games only: extra contrast (2048/tetris) |
| red — 1             | `#ff5030` | Frank warnings / alerts |

The amber/cream/teal accents exist to fix contrast where the single-hue palette
made distinct things look identical (chess white-vs-black, 2048 tiles, tetris
pieces, sudoku givens). They are **not** the old dropped amber/green *theme* —
the core body stays base yellow.

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
