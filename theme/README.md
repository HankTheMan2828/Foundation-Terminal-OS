# Theme — CRT phosphor look (spec §2, §8)

Amber primary / green alt, scanlines, glow, monospace bitmap font (Terminus).
Approved defaults this session (docs/OPEN-QUESTIONS.md §7); all tunable later
from the Hub's Settings → Theme screen.

Two layers combine for the look:

1. **kitty** (`system/etc/foundationhub/kitty.conf`, installed to `/etc/foundationhub/`) —
   sets the palette, font, no window chrome, block cursor. Amber by default.
   `colors-green.conf` here is the alt palette Settings can swap to.
2. **The TUI itself** (`hub/foundationhub/theme.py`) — draws the frame/bezel, the
   scanline dimming on alternate rows, and the "glow" via inverse highlight on
   the selected row. It picks real amber (#FFB000) / phosphor green (#33FF66)
   when the terminal can redefine colors, and degrades to yellow/green
   otherwise.

Deferred to the dedicated visual pass (spec §11.10): a shader-based bloom/glow
and true scanline overlay (kitty has no native CRT shader; options are a
`kitty` graphics-protocol overlay or running under a compositor effect). Not
in v1.
