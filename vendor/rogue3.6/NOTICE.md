# Rogue 3.6 (1981, Berkeley original) — vendored source

Feedback item 2 ([docs/FEEDBACK-FIRST-HARDWARE-RUN.md](../../docs/FEEDBACK-FIRST-HARDWARE-RUN.md)):
operator decision was to download upstream, not build in-house. This directory
vendors the real 1981 Rogue source so it can be compiled into an Arch package
**at ISO build time** (`image/build-iso.sh`) and baked into the offline
package repo — never fetched on the target machine (see `PKGBUILD`).

- **Upstream:** https://github.com/RoguelikeRestorationProject/rogue3.6
- **Vendored commit:** `f36912c4744b83ca79f9f5489a0528a2f0683996` (2011-09-29)
- **Fetched:** 2026-07-03
- **License:** BSD 3-clause — see `src/LICENSE.TXT`, reproduced verbatim.
  Covers Michael Toy, Ken Arnold, Glenn Wichman (original authors, 1980-1981)
  plus the Nicholas J. Kisseberth (`state.c`/`mdport.*`) and David Burren
  (`xcrypt.c`, FreeSec libcrypt) BSD grants folded into the same restoration.
  The license permits redistribution (source and binary) with attribution;
  `PKGBUILD` installs `LICENSE.TXT` to `/usr/share/licenses/rogue3.6/`.
- **Not modified.** `src/` is the upstream source tree as-is (Windows/MSVC
  project files dropped — `.sln`/`.vcproj` are dead weight on this OS).
  `PKGBUILD` only overrides the score-file path via `CFLAGS` (see below); no
  game logic is touched. This is a download-and-package job, not a build —
  see the operator decision above.
- **Score file / shared board:** the upstream Makefile hardcodes a
  cwd-relative `rogue36.scr` with no setgid support (unlike 5.4's autotools
  build). `PKGBUILD` recompiles `SCOREFILE` to the absolute path
  `/var/lib/rogue/rogue36.scr` and installs the binary setgid `games`
  (Arch's `filesystem` package ships a `games` group by default) so every
  account shares one top-ten board — the authentic 1981 behavior, and
  consistent with this repo's machine-wide-scores decision for the in-house
  games (see `docs/ROGUELIKE-DESIGN.md` §2.1, §5 item 4).
