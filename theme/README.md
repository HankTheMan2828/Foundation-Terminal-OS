# Theme — CRT phosphor look (spec §2, §8)

Amber primary / green alt, scanlines, glow, monospace bitmap font (Terminus).
Approved defaults this session (docs/OPEN-QUESTIONS.md §7); all tunable later
from the Hub's Settings → Theme screen.

Two layers combine for the look:

1. **The kernel console itself** (`system/usr/local/bin/foundationhub-session`)
   — sets the bitmap console font (`setfont ter-v16b`, Terminus) and retunes
   the VT's 16-color palette to phosphor hues via the kernel's `\e]PXRRGGBB`
   escape. Amber by default, green alt. This is a plain Linux-console
   feature: no compositor, no graphical terminal, no GPU.
2. **The TUI itself** (`hub/foundationhub/theme.py`) — draws the frame/bezel, the
   scanline dimming on alternate rows, and the "glow" via inverse highlight on
   the selected row. It picks real amber (#FFB000) / phosphor green (#33FF66)
   when the terminal can redefine colors, and degrades to yellow/green
   otherwise (which, on the VT, the session script has already retuned to the
   same phosphor hues).

The kitty palette configs (`kitty.conf`, `colors-green.conf`) moved to
`profiles/zenbook-duo-2024/system/etc/foundationhub/` — they only exist for
that profile's display-stack plugin; the core has no kitty.

Deferred to the dedicated visual pass (spec §11.10): bloom/glow and a true
scanline overlay. On the bare VT the options are character-level effects only
— anything shader-based would belong to a profile's display stack, never the
core. Not in v1.
