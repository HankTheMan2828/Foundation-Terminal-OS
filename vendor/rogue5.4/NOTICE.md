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
- **Not modified.** `src/` is the upstream source tree as-is (Windows/MSVC
  project files, the `.desktop`/`.png` icon, and `rogue.spec` RPM metadata
  dropped — none apply to this OS's kernel-console-only model). `PKGBUILD`
  only passes the project's own `./configure` flags (program name, setgid
  group, score/lock file paths) — no game logic is touched.
- **Score file / shared board:** built with `--enable-setgid=games
  --enable-scorefile=/var/lib/rogue/rogue54.scr
  --enable-lockfile=/var/lib/rogue/rogue54.lck` — the upstream build system's
  own mechanism for a shared top-ten board (setgid `games` binary, group-
  writable scorefile; Arch's `filesystem` package ships a `games` group by
  default). One board per vintage, per account name — the authentic 1985
  behavior, and consistent with this repo's machine-wide-scores decision for
  the in-house games (see `docs/ROGUELIKE-DESIGN.md` §2.1, §5 item 4).
