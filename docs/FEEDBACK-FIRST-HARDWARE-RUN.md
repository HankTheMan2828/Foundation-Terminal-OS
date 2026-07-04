# Operator feedback — first successful hardware run (2026-07-03, mini PC)

The first end-to-end hardware install (USB creator → boot → installer →
Home Hub) succeeded on the mini PC testbed. This is the operator's raw
feedback from that first session, itemized for follow-up work. Items are
UX-focused; none block installs.

## 1. Text size (setup + settings)  — HIGH — ✅ FIXED (2026-07-03)
- The console text is too small. **Default should be twice the current
  size**, and the installer/first-boot setup should *ask* about text size.
- Users must also be able to change text size later in **Settings**.
- Pointers: the console font is set with `setfont` (currently
  `ter-v16b` — `ter-v32b` is the 2× Terminus bitmap; see
  `install/02-console-kiosk.sh` / theme). A per-user setting needs a hook in
  `hub/foundationhub/screens/settings.py` plus persistence.
- Fixed: text size is now a VT-wide `setfont` face persisted in one
  operator-writable file, `/etc/foundationhub/console-font`.
  - **Default is now `ter-v32b`** (16×32, the 2× face) — the session wrapper
    (`system/usr/local/bin/foundationhub-session`) reads the file and falls
    back to that default.
  - The **installer asks** ("normal / large / extra large", default 2×) and
    seeds the file via `FOUNDATION_CONSOLE_FONT` →
    `install/02-console-kiosk.sh`.
  - **Settings** (`FUNCTIONS → TEXT SIZE`) changes it live and persists it —
    logic in the new `hub/foundationhub/consolefont.py`
    (`hub/tests/test_consolefont.py`). NOTE: the "settings.py" pointer was
    stale — the settings area is Functions Control (`screens/functions.py`).
    The setting is machine-wide (like theme/brightness), not per-user: real
    per-account sessions are still `[TODO(hardware)]`, and `setfont` is a
    VT-global op, so a true per-user font waits on that.

## 2. Rogue is missing from Recreation  — DOWNLOAD, don't build — ✅ FIXED (2026-07-03)
- Operator looked for **Rogue (the original)** and the **1985 version**
  (the visually improved release) and couldn't find them.
- **Operator decision (2026-07-03): do NOT build these in-house.** Both
  versions are available on the web — download them, integrate into the
  Recreation area, and make sure they're **stable on this OS** (kernel VT,
  curses, no display stack). That's the whole scope.
- This supersedes the in-house build plan for Rogue specifically
  (`docs/ROGUELIKE-DESIGN.md` stays parked; the "Foundation Depths"
  modernized variant remains a possible future in-house project).
- Integration constraint: the OS installs **offline** from the ISO's
  embedded package repo — upstream Rogue must end up installable that way
  (official-repo/AUR package baked into the offline repo, or source
  vendored and built at ISO build time — not fetched on the target).
- Fixed: both real upstream games, no in-house code. Source vendored
  verbatim from the Roguelike Restoration Project's restorations —
  `vendor/rogue3.6/` (1981, Berkeley original, BSD-3) and `vendor/rogue5.4/`
  (1985, the authors' finished version, BSD-3) — each with a `NOTICE.md`
  (upstream URL, exact commit vendored, license text location) and a
  `PKGBUILD` that builds the vendored source into a real Arch package.
  `image/build-iso.sh` now runs `makepkg` for both (as a throwaway
  unprivileged build user — makepkg refuses root) **at ISO build time** and
  copies the resulting `.pkg.tar.*` into the same offline repo directory the
  rest of the OS's packages land in, before `repo-add` runs — so pacstrap
  installs them from the ISO's embedded repo exactly like every other
  package, no network on the target. Package names `rogue3.6`/`rogue5.4`
  added to `install/packages.txt` (same mechanism as `nethack`, just above
  it). Recreation's roguelikes bucket
  (`system/etc/foundationhub/recreation.toml` + the `_DEFAULT` fallback in
  `hub/foundationhub/screens/recreation.py`) now lists **Rogue (1985)**
  (`rogue54`, default/first) and **Rogue (1981, OG)** (`rogue`) above
  NetHack, which stays as the interim third entry (not asked to retire it).
  - **Stability on this OS:** both are plain terminfo/ncurses console
    programs with no GUI/display-stack dependency — `main()` calls
    `initscr()`/raw terminal I/O only, same category as NetHack, which
    already runs fine on the kernel VT here. Not yet smoke-tested on real
    hardware in this session (no Arch/makepkg toolchain in this dev sandbox);
    next real-hardware pass should confirm both launch and render correctly
    from Recreation and that the ISO's `makepkg` step succeeds cleanly.
  - **Shared score board:** both binaries are installed setgid `games` with
    an absolute scorefile/lockfile under `/var/lib/rogue/`, group-writable —
    the games' own upstream mechanism for one shared top-ten, matching this
    repo's machine-wide-scores decision (item 6) in spirit. This is each
    game's *native* score file (its own `S`core command), separate from the
    Hub's Python `HighScoresScreen`/`highscores.py` — not wired into that
    display, since parsing the C scoreboard format is out of scope here.
  - **Licenses — redistribution confirmed.** Both are BSD 3-clause
    (Toy/Arnold/Wichman, plus folded-in BSD grants for `state.c`/`mdport.*`
    and `xcrypt.c`) — permits source and binary redistribution with
    attribution, which is exactly what's happening (unmodified vendored
    source, license text shipped in the package at
    `/usr/share/licenses/rogue3.6/` and `/usr/share/licenses/rogue5.4/`).
    Full text in each vendor dir's `src/LICENSE.TXT`.

## 3. Arcade games: center + border  — polish — ✅ FIXED (2026-07-03)
- Games play great. They should render **centered on screen** with a
  **visible border** around the playfield (currently corner-anchored /
  borderless on large consoles).
- `games/foundation_arcade/`.
- Fixed: new `chrome.draw_playfield()` centers the playfield in the
  chrome's content area and draws a border, wired into all five games
  (Snake, Falling Blocks, 2048, Sudoku, Invaders).

## 4. Esc-to-go-back has a noticeable delay  — polish, quick fix — ✅ FIXED (2026-07-03)
- Backspace navigates back near-instantly; **Esc has a lag**.
- Almost certainly curses' default escape-sequence wait (`ESCDELAY`,
  default ~1000ms). Set it low (~25ms) at Hub startup
  (`hub/foundationhub/app.py`) and in the standalone games/media apps.
- Fixed: `curses.set_escdelay(25)` set at all four curses entry points
  (Hub, foundation-arcade, foundation-chess, foundationmedia).

## 5. Notes area: rename + new-note flow  — HIGH — ✅ FIXED (2026-07-04)
- The area is currently labeled **"text editor" — confusing**. Rename to
  **"Notes Area"**.
- Flow: opening it goes to the **folder of notes to choose from**. The top
  first option — visually separated (a little space) from the note list —
  is **`--- create new note ---`**; pressing Enter on it prompts **"Name?"**
  then proceeds into the editor.
- Later (explicitly deferred by operator): **folders** and a **search**
  feature.
- `hub/foundationhub/screens/notes.py` + `editor.py`, menu labels in
  `labels.py`.
- Fixed: the Programs entry is now **NOTES AREA** (`labels.PROG_NOTES`,
  was the bare "TEXT EDITOR" scratch pad). It opens the new
  `NotesAreaScreen` (`screens/notes.py`): **`--- create new note ---`** on
  top, a blank spacer, then the notes. Enter on the top row prompts
  **`NAME?`** and drops straight into the editor (the seeded note is written
  on SAVE, as with every other note). A name that collides with an existing
  note just opens it instead of dead-ending.
  - The area **shares the tagged-notes store** (`notesdb.NOTES_DIR`) so
    there is one notes folder on disk, not a second parallel one. Note→path
    resolution is now the shared `notesdb.note_path()`
    (`hub/tests/test_notesdb.py`), reused by both the Notes Area and
    Tagged Notes.
  - **Folders and search are deferred**, per the operator (search still
    lives in Personal File → SEARCH RECORDS).

## 6. Game scores: ONE system-wide board, shown in Recreation  — HIGH — ✅ FIXED (2026-07-04)
- **Scoring is SYSTEM-WIDE ONLY — NEVER per user** (operator correction
  2026-07-04: no per-user score lists, no per-user filtering, ever).
- There is **one global high-score table per game** for the whole machine;
  each entry **marks which user set it** (name attached to the score).
- Scores must **not** appear in the file/folder area; they show as a
  **list in the games (Recreation) area**.
- Fixed: `games/foundation_arcade/scores.py` now writes ONE machine-wide
  file, `/var/lib/foundationhub/highscores.json` (`{game: {"score", "name"}}`)
  — outside any account's quota'd `~/.local/share/foundationhub` space, so it
  never shows up in a user's files (`install/08-games.sh` creates the dir,
  owned by the operator). `record_score`/`best_score` call sites in Snake,
  Falling Blocks, 2048, Sudoku, and Invaders are unchanged; only the store
  moved from per-user to system-wide, attributing each best score to
  `scores.active_username()` unless told otherwise.
  - Recreation gained a new **HIGH SCORES** entry
    (`hub/foundationhub/screens/recreation.py`'s `HighScoresScreen`), reading
    the same file via a small independent reader
    (`hub/foundationhub/highscores.py` — the Hub and games are separate
    distributions, so this mirrors how `session.py` reads Frank's ledger
    file directly rather than importing frankd).
  - **Chess folded in too** (operator direction 2026-07-04, after the arcade
    pass landed): `games/foundation_chess/stats.py` now keeps ONE
    machine-wide win/loss/draw tally in `/var/lib/foundationhub/chess.json`
    instead of a per-user record — same state dir the arcade's high scores
    use, same "never per user" rule. Chess has no single beatable score (a
    tally isn't a peak record), so it isn't folded into the same
    score-board rows; it gets its own **W/L/D** line at the bottom of the
    **HIGH SCORES** screen instead (`highscores.load_chess_record()`).

## 7. Dated-entry feature for general notes  — feature — ✅ FIXED (2026-07-03)
- The **personal file area's dated-entry thing** (journal-style entries)
  should also exist in the **general notes area**, under a different name.
- Operator picked the label **"Dated Entries"** and added two requirements
  while deciding: entries carry an **HH:MM timestamp** so several can exist
  per day (unlike the personal journal's one-file-per-day), and notes need
  **a rename option from inside the editor**, not just from the list.
- Fixed: `hub/foundationhub/notesdb.py` gained a separate `DATED_DIR` tree
  (`list_dated`, folded into `search()`) so the general area's entries never
  share files with the personal journal's `JOURNAL_DIR`. NOTES AREA
  (`hub/foundationhub/screens/notes.py`'s `NotesAreaScreen`) gained a pinned
  **DATED ENTRIES** row leading to `DatedAreaScreen`; "new entry" always
  creates a fresh `YYYY-MM-DD-HHMM.md` file rather than reusing one per day.
  Labels: `labels.NOTES_AREA_DATED*`.
- Also fixed, in the same pass: the in-house editor's Esc menu gained a
  **RENAME** option (`SAVE / RENAME / DISCARD / RETURN`) that prompts for a
  new name, slugifies it (`notesdb.slugify`), and renames the file on disk —
  works for any note opened in the editor, not just dated entries.

## 8. Home Hub information architecture  — think piece — ✅ FIXED (2026-07-03)
- The ordering of the Home Hub and its sub-areas **"feels a little
  hectic."** Operator explicitly invites proposals for re-working the
  ordering/grouping of the Hub and sub-areas. Draft options, don't just
  pick one — menu wording is operator-approval territory
  (`OPEN-QUESTIONS.md`).
- Process: three orderings were drafted (reorder-only / rename-and-merge /
  "rooms"). Operator chose the rename-and-merge direction with changes.
- Fixed — the reworked IA (canonical listing now in `BUILD-SPEC.md` §5):
  - **Top level is five entries:** `PROGRAMS · RECREATION · SETTINGS · LOGS ·
    POWER` (was eight). Diagnosis of "hectic": notes lived in two places at two
    depths sharing one on-disk folder; "settings" was split across FUNCTIONS +
    STATUS; the root mixed registers in an arrhythmic order.
  - **Notes consolidated under Programs.** The old top-level `PERSONAL FILE`
    and the duplicate Programs `NOTES AREA` merged into one **NOTES** page with
    two purpose sections — **Work** first, **Personal** last, set apart by a
    blank gap. Work has plain notes + timestamped **Dated Entries**; Personal
    has plain notes + the one-per-day **Dated Journal** (kept, per operator;
    now says "TODAY'S NOTE ALREADY EXISTS" and opens it when today's is made).
    Programs order: **Notes · Notes Search · Files · Media · Monitor**.
  - **On-disk split → File Manager.** Each section is its own folder under the
    account dir (`work/`, `personal/`, each with a `dated/` or `journal/`
    subfolder). The File Manager is rooted there, so it shows `work/` and
    `personal/` as two clean folders — the "separate folders in the file
    viewer" ask. A one-time `notesdb.migrate_legacy()` moves any pre-rework
    `notes/`/`dated/`/`journal/` into the new layout (idempotent, non-destructive).
  - **Notes Search is its own program** (Programs → NOTES SEARCH): asks
    "include Personal notes?", **defaults to Work-only**.
  - **FUNCTIONS → SETTINGS.** `NETWORK` (an action) moved out of Status into
    Settings; the read-only **System Status** readout became a leaf inside
    Settings (no longer a top-level entry).
  - **Assistant hidden** from the menu for now (screen code retained; one-line
    revert in `screens/__init__.build_home`).
  - Code: `screens/__init__.py`, `screens/programs.py`, `screens/functions.py`,
    `screens/status.py`, `screens/notes.py`, `notesdb.py`, `labels.py`; tests
    in `hub/tests/test_notesdb.py` (section layout + migration). Note the
    trade-off: list-based note delete/rename dropped from the notes screens —
    rename lives in the editor, delete in the File Manager (one-editor / one
    file-op surface).

## 9. Highlight bars don't always reach the screen edge  — polish — ✅ FIXED (2026-07-03)
- Some selection/highlight bars stop short of the right edge; make bar
  width consistent (full width) across all screens.
- Root cause: the in-house editor's Esc menu (SAVE/DISCARD/RETURN —
  used on every journal/notes/scratch screen) padded its highlight to a
  hardcoded 20 columns instead of the window width. Fixed in
  `hub/foundationhub/editor.py` to scale like every other Hub menu
  (`ui.Menu.draw`'s `w - 2*left`).

## 10. BUG: colors shift to "super amber" after a few interactions
- Reproduced by the operator: after a few clicks inside a **user's area**,
  the palette shifts to a much more saturated amber.
- Smells like a color-pair/attribute leak (re-initializing pairs, or bold
  attribute stacking) in `hub/foundationhub/theme.py` / screen redraw
  paths. Needs investigation — find the repro, then the leak.

## 11. Update system (USB and/or network)  — NEW SUBSYSTEM, design first
Operator direction (2026-07-03, right after the first successful install):

- The installed OS needs **a way to update**: over the internet **or via
  USB**.
- **Transport policy is a per-machine setting**: in a company setting the
  operator would restrict updates to **USB or hardwire (ethernet) only**;
  **wireless should also exist, enabled/configured from the Settings
  area** — i.e. allowed transports are configurable, not hardcoded.

Design sketch to start from (not approved yet):
- **USB path — reuse the installer medium.** The release ISO already
  carries the full repo + offline package repo. `foundation-install`
  could detect an existing Foundation TerminalOS on disk and offer
  **UPDATE** (re-run `install/run-all.sh` + pacman upgrade from the
  embedded repo, preserving `/home`, accounts, Frank state) alongside the
  full ERASE install. Zero new artifacts; the USB creator already exists.
- **Network path:** fetch the latest GitHub release (or a pacman repo)
  from inside the OS — needs a Settings-area screen: check for updates,
  show version, apply. Respect the transport policy (usb / wired-only /
  wireless-allowed), with wireless setup (nmtui or in-house) reachable
  from Settings only when policy allows.
- **Trust questions for OPEN-QUESTIONS:** what verifies an update
  (checksums are on the release; signing?), who may trigger one (operator
  only? Frank-gated?), and updates must not create a path that weakens
  Frank isolation.

## Also fixed during this run (already committed, for context)
- Exec bits stripped from the embedded repo by mkarchiso → restored at
  install time (`foundation-install`), plus five files' modes fixed in git.
- `install/03` ran `grub-mkconfig` before `/boot/grub` existed on the
  bare-metal path → creates the dir now.
- Root-password prompt now echoes `*` per keystroke.
- Live ISO: root unlocked (rescue shells work), gpt-auto generator masked,
  and the initramfs preset actually wires in the archiso config (the bug
  that made every pre-2026-07-03 ISO unbootable on hardware).
