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

## 2. Rogue is missing from Recreation  — DOWNLOAD, don't build
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

## 6. Game scores: belong to the user, live in Recreation  — HIGH
- Scores should be **attributed to the user** who set them.
- Scores must **not** appear in the file/folder area; they should show as a
  **list in the games (Recreation) area**.

## 7. Dated-entry feature for general notes  — feature
- The **personal file area's dated-entry thing** (journal-style entries)
  should also exist in the **general notes area**, under a different name.

## 8. Home Hub information architecture  — think piece
- The ordering of the Home Hub and its sub-areas **"feels a little
  hectic."** Operator explicitly invites proposals for re-working the
  ordering/grouping of the Hub and sub-areas. Draft options, don't just
  pick one — menu wording is operator-approval territory
  (`OPEN-QUESTIONS.md`).

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
