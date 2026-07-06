# Rogue 5.4.5 (1985, the authors' finished version) — vendored source

Feedback item 2 ([docs/FEEDBACK-FIRST-HARDWARE-RUN.md](../../docs/FEEDBACK-FIRST-HARDWARE-RUN.md)):
operator decision was to download upstream, not build in-house. This directory
vendors the real 1985 Rogue source so it can be compiled into an Arch package
**at ISO build time** (`image/build-iso.sh`) and baked into the offline
package repo — never fetched on the target machine (see `PKGBUILD`).

- **Upstream:** https://github.com/RoguelikeRestorationProject/rogue5.4
- **Vendored commit:** `9d0dcccc8ec82454bd4d4310f4638985a4726d83` (2011-09-29)
- **Fetched:** 2026-07-03
- **License:** BSD 3-clause — see `src/LICENSE.TXT`, reproduced verbatim.
  Covers Michael Toy, Ken Arnold, Glenn Wichman (original authors,
  1980-1983/1985/1999 recovery) plus the Nicholas J. Kisseberth
  (`state.c`/`mdport.*`) and David Burren (`xcrypt.c`, FreeSec libcrypt) BSD
  grants folded into the same restoration. The license permits redistribution
  (source and binary) with attribution; `PKGBUILD` installs `LICENSE.TXT` to
  `/usr/share/licenses/rogue5.4/`.
- **`src/` is the upstream source tree, verbatim** (Windows/MSVC project files,
  the `.desktop`/`.png` icon, and `rogue.spec` RPM metadata dropped — none
  apply to this OS's kernel-console-only model). Nothing in `src/` is edited in
  the repo. `PKGBUILD` passes the project's own `./configure` flags (program
  name, setgid group, score/lock file paths) and applies **build-time patches
  to a throwaway copy** (`prepare()`; the repo tree is never touched):
  - **`tstp()` ncurses fix** — swaps two pokes at ncurses' now-opaque WINDOW
    fields for the public `wmove(curscr, …)`; behavior-identical, needed to
    compile against modern ncurses.
  - **Color** (operator direction 2026-07-05) — upstream 5.4 is monochrome, so
    on this OS it looked identical to the 1981 build. The color layer in
    [`color/xcolor.{h,c}`](color/) (not upstream) is copied into the build and
    wired in: `rogue.h` includes it after `extern.h`, `main.c` starts color
    after the gameplay `initscr()`, and `Makefile.in` links it. It wraps the
    character-plotting primitives to attach a classic PC-Rogue color per
    symbol; color lives only in the attribute bits, which the game masks off
    with `CCHAR()` when reading the map back — purely cosmetic, no game logic.
  - **Esc-to-exit** (operator direction 2026-07-05) — Esc in the top-level
    command loop invokes the game's own `quit(0)` "really quit?" gate (mirrors
    the existing `Q` command); the kiosk otherwise had no way out.

  The `color/` sources are original to this repo (MIT-compatible, authored
  here); everything under `src/` remains BSD-3 upstream.
- **Score file / shared board:** built with `--enable-setgid=games
  --enable-scorefile=/var/lib/rogue/rogue54.scr
  --enable-lockfile=/var/lib/rogue/rogue54.lck` — the upstream build system's
  own mechanism for a shared top-ten board (setgid `games` binary, group-
  writable scorefile; Arch's `filesystem` package ships a `games` group by
  default). One board per vintage, per account name — the authentic 1985
  behavior, and consistent with this repo's machine-wide-scores decision for
  the in-house games (see `docs/ROGUELIKE-DESIGN.md` §2.1, §5 item 4).
