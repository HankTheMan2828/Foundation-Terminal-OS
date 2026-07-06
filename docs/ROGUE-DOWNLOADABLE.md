# Rogue (1985) — downloadable graphical build (skeleton)

Status: **not shipped.** This is a placeholder/hook for a future user-provided
build. The operator will dig into this themselves (decision 2026-07-06).

## What the operator wants

The graphical **DOS/PC (Epyx) Rogue** look: green `·` floors, gray hatched `▒`
corridors, box-drawn walls, a smiley-face `☺` player, and glyph items
(`☼` food, `♪` potions, `↑` weapons, …) in color — the classic 1985 PC version,
not the monochrome ASCII terminal Rogue.

## Why it isn't vendored (the blocker)

Everything else the OS ships is redistributable (the 1981 Rogue is BSD-3; see
`vendor/rogue3.6/NOTICE.md`). The exact-match open-source port of the PC version
is **roguepc** (see Reference below), but it carries **no license at all** and
derives from the *commercial* Epyx/AI Design PC Rogue — so it cannot be baked
into the offline ISO, which redistributes every game binary. The BSD Rogue 5.4
we briefly vendored is monochrome ASCII, which just duplicated the 1981 game
(the operator's original "two of the 1981 games" report), so it was dropped
2026-07-06 rather than shipped as a look-alike.

Two clean paths, for whoever picks this up:
1. **License it.** Get a redistribution grant for roguepc (or the PC Rogue
   sources), then vendor it like `vendor/rogue3.6` and flip the hook below.
2. **Build the look on redistributable source.** Take a BSD Rogue (e.g. the
   already-known `vendor/rogue3.6`, or upstream rogue5.4) and add our own
   DOS-style display layer — CP437/Unicode glyphs + color — as a build-time
   patch. This is original code on BSD source, so it's shippable. It's the
   bigger engineering job (wide-char/ncursesw or a console-font swap; see
   "Rendering on the kernel VT" below).

## The skeleton that's already here

- **Menu slot.** `system/etc/foundationhub/recreation.toml` (and the `_DEFAULT`
  fallback in `hub/foundationhub/screens/recreation.py`) list a **Rogue (1985)**
  entry that execs `rogue54`, marked `downloadable — not installed`. With no
  `rogue54` on the system the Hub shows a graceful "downloadable graphical
  build" notice instead of launching — so the slot is visible and self-
  explanatory, and nothing is shipped.

## Wiring a real build in later (the hook)

When a redistributable `rogue54` exists:
1. Add its vendored source under `vendor/rogue5.4/` with a `PKGBUILD` +
   `NOTICE.md` (provenance + license), mirroring `vendor/rogue3.6/`.
2. Add `rogue5.4` back to the `VENDORED=(…)` array in `image/build-iso.sh` and
   to `install/packages.txt` so it's built at ISO time and pacstrapped offline.
3. Drop the `hint`/`missing_hint` from the recreation.toml `rogue54` entry.
   That's it — the menu already points at `rogue54`.

## Rendering on the kernel VT (the real constraint)

The OS draws on the **kernel virtual console** with a *bitmap* font (Terminus,
`ter-v32b`), not a graphical terminal with a TrueType font. So a Unicode build
(like roguepc's default) only renders the fancy glyphs if the loaded console
font contains them at the right code points. The two workable approaches:
- **CP437 console font + 8-bit map** while the game runs (`setfont` a VGA/CP437
  face + leave UTF-8), restoring the OS font/UTF-8/phosphor palette on exit — a
  launcher wrapper, the same pattern the Hub uses elsewhere for per-launch VT
  state. This gives the authentic DOS look natively.
- **A Unicode console font** carrying `☺`/`☼`/`♪`/`▒`/box-drawing at their
  Unicode code points, with the game emitting those via `ncursesw`.

Either way it needs testing on real hardware — it can't be verified in the dev
sandbox.

## Reference (evaluate, don't ship as-is)

- roguepc — port of the PC-DOS Epyx Rogue to modern Linux/curses, CP437→Unicode,
  color: https://github.com/MestreLion/roguepc  (⚠ no license — see blocker above)
- Rogue Clone IV — DOS/Windows, configurable UNIX/IBM-PC look:
  https://rogueclone.sourceforge.net/
