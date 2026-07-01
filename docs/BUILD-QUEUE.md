# Foundation TerminalOS — Build Queue: In-House Application Sessions

Instructions for future working sessions. Each § below is a self-contained
spec: a session prompt will name one section; read GLOBAL CONSTRAINTS plus
that section and build exactly that. Each section carries a **recommended
Claude model** (set in the model picker before starting the chat) sized to
the session's difficulty — judgment-heavy/novel architecture → Fable 5,
deep single-domain reasoning → Opus 4.8, well-scoped pattern-following
builds → Sonnet 5. Decisions behind all of this:
`docs/OPEN-QUESTIONS.md` §10 (in-house mandate, hybrid model, redundancy
cuts) and `docs/USERS.md` (multi-user model). Update `docs/STATUS.md` row 12
as items land.

## GLOBAL CONSTRAINTS (apply to every section)

- **In-house means in-house.** The point of each session is to *retire* an
  open-source stand-in. When the replacement is functional: remove the
  stand-in from the relevant screen, remove its package from
  `install/packages.txt`, and note the retirement in `docs/STATUS.md`.
- **Pure-stdlib Python + curses**, matching the existing zenhub style:
  screens compose the widgets in `hub/zenhub/ui.py`; every user-visible
  string goes in `hub/zenhub/labels.py`; colors only via `zenhub.theme`
  semantic pairs (amber/green CRT — never raw curses colors). Fallout-4
  terminal / Aperture Science register: highlight an option, press Enter.
- **Hybrid model (decided):** notes, file manager, and system monitor are
  *native Hub screens* inside `hub/zenhub/`; media and games are *separate
  in-house programs* in their own top-level dirs, launched via
  `app.py Launch(...)` and installed by the install scripts.
- **Multi-user:** all user data is per-account. Get the active account via
  `zenhub.session.get_active_account()`; follow the `_user_dir()` pattern in
  `hub/zenhub/screens/notes.py`. Users must never see each other's data.
  Storage is quota'd — respect the "fixed allotment" story (docs/USERS.md).
- **Nothing is exempt from Frank.** No private zones, no Frank-visible
  surfaces removed. Never surface Frank detail beyond what the ledger
  already shows (timestamps only).
- **Portability:** this must eventually run on much weaker hardware
  (console-mode tier, then Pocket8086). No heavy dependencies, no pip
  requirements for core function, be frugal with redraw loops.
- **Dev environment:** develop off-device. On Windows use `py` +
  `windows-curses` (already installed); dev knobs: `ZENHUB_USERS=<path>`
  (writable registry), `ZENHUB_USER=<name>` (skip login),
  `ZENHUB_DATA=<path>` (data root). Run with `cd hub && py -m zenhub`.
- **Tests:** keep logic separable from curses and unit-test it headlessly
  (buffer ops, parsing, search, playlists…). Frank's suite must stay green:
  `cd frank && py -m pytest` (2 AF_UNIX IPC tests fail on Windows only —
  expected, ignore).
- **Docs discipline:** anything user-facing that needs the operator's
  sign-off gets a ⬜ line in `docs/OPEN-QUESTIONS.md`, not a silent decision.

---

## §1 NOTES SUITE  ← build first

**Recommended model:** Fable 5 — foundational session; the editor widget's
buffer/cursor/wrap logic is subtle and everything later reuses it.

**Goal:** the full in-house notes system (a key aspect of the OS) and, with
it, THE system text editor. Decided: "Full in-house notes suite" — built-in
curses editor + note browser: dated journal, tagged notes, search by tag and
text, all inside the Hub. No external editor, ever.

Build:
1. `hub/zenhub/editor.py` — a reusable curses text-editor widget (not a
   screen): line buffer, cursor movement (arrows + vim hjkl where sane),
   insert/delete, scrolling, optional soft wrap, save, dirty-flag, Esc menu
   (SAVE / DISCARD / RETURN). Status line shows file + position. This widget
   is the one-editor policy: it later opens files for the file manager too.
   Keep the buffer logic in a plain class (no curses) so it's unit-testable.
2. Rework `hub/zenhub/screens/notes.py` (PERSONAL FILE):
   - DATED JOURNAL — opens today's `journal/YYYY-MM-DD.md` in the editor;
     add a browsable list of past entries (newest first).
   - TAGGED NOTES — native list of `notes/*.md` (replaces the ranger
     launch): create, rename, delete, open in the editor.
   - SEARCH — search across journal+notes by tag and free text.
   - Tags: inline `#tag` tokens in the note body; parser in a testable
     module (e.g. `hub/zenhub/notesdb.py` — scanning, tag index, search).
3. Files stay plain `.md` on disk (portable, greppable, quota-friendly).
   Per-user via the existing `_user_dir()` pattern.
4. Retire nvim: Programs → TEXT EDITOR now opens the in-house editor (on a
   scratch file or the notes dir); remove `neovim` from
   `install/packages.txt`; drop the `EDITOR` env fallback in notes.py.
5. Tests for buffer ops, tag parsing, and search. Update STATUS.md.

## §2 FILE MANAGER (native Hub screen)

**Recommended model:** Sonnet 5 — well-scoped screen following existing
patterns; the one sharp edge (path-scoping guard, destructive-op confirms)
is spelled out below.

**Goal:** retire ranger. A native PROGRAMS → FILE MANAGER screen scoped to
the account's own data space.

Build:
1. `hub/zenhub/screens/files.py` — directory listing (dirs first, sizes,
   mtimes), navigate in/out, and operations: open (text files → the §1
   editor), rename, copy, move, delete (confirm prompt), new directory.
2. Scope: the account's own space only (its `_user_dir()` tree; on target,
   its quota'd home). Never a system-wide browser — the operator has no
   business in `/etc`. No path escapes (`..` stops at the root).
3. Quota readout: header shows used vs. tier allotment (e.g.
   `12.3 MB / 5 GB`) — the visible face of the fixed-allotment rule.
   Tier data: `zenhub.accounts.TIERS[acct.tier].quota_bytes`.
4. Wire in: Programs FILE MANAGER item; notes TAGGED NOTES already native
   after §1 — keep them consistent. Remove `ranger` from packages.txt.
5. Tests: path-scoping guard, size formatting, operation planning logic.

## §3 SYSTEM MONITOR (native Hub screen)

**Recommended model:** Sonnet 5 — /proc parsing is formulaic and the spec is
tight. (Haiku 4.5 is a viable budget option if the session stays strictly to
spec.)

**Goal:** retire btop. A native PROGRAMS → SYSTEM MONITOR screen.

Build:
1. `hub/zenhub/screens/monitor.py` + a testable `hub/zenhub/sysinfo.py`
   reading `/proc` directly (stdlib only): overall CPU% (delta of
   /proc/stat), per-core optional, memory (/proc/meminfo), uptime, load,
   process list (pid, name, cpu%, mem) sorted by CPU, network rx/tx rates
   (/proc/net/dev deltas).
2. View-only v1: no kill/renice (that's root/Frank territory, and the
   operator shouldn't have it). Refresh ~2s, cheap redraws.
3. Degrade gracefully off-Linux: on the Windows dev box show an honest
   "host does not expose /proc — display only on target" panel rather than
   crashing (same graceful-degradation pattern as session.py helpers).
4. Remove `btop` from packages.txt. Tests for the /proc parsers with
   fixture text.

## §4 ZENMEDIA (separate in-house program)

**Recommended model:** Fable 5 — opens with a real architecture decision
(playback backend) and the likely ctypes/ALSA work is the trickiest code in
the queue.

**Goal:** the ONE media player (cmus+mpv were both dropped for it). A
standalone in-house TUI program at top-level `media/zenmedia/`, launched by
the already-wired Programs MEDIA item (`Launch(["zenmedia"])`).

Build:
1. **First: settle the playback backend — this is the session's opening
   decision, present options to the operator before coding.** Pure-stdlib
   audio *decode* is only realistic for WAV; candidates: (a) ALSA PCM via
   ctypes + stdlib WAV/AIFF (fully in-house, format-limited), (b) shell out
   to `ffmpeg`/`ffplay` as a decode *engine* under an in-house UI (broad
   formats; ffmpeg is a build tool more than a borrowed app), (c) both —
   stdlib path as the Pocket8086-tier fallback. Record the pick in
   OPEN-QUESTIONS.md.
2. TUI: library view over the account's media dir (per-user!), playlist
   queue, play/pause/stop/seek/volume, now-playing line, same CRT theme
   (factor shared chrome from `zenhub/ui.py`/`theme.py` rather than
   duplicating — acceptable to import zenhub as a library).
3. Install wiring: new `media/` dir installed like `hub/` (see
   `install/04-hub.sh` pattern); add a bin shim `zenmedia`.
4. Audio first; video explicitly out of scope for v1 (console tier may
   never do it). Tests for playlist/library logic.

## §5 GAMES (separate in-house programs — may span several chats)

**Recommended models:** zenarcade → Sonnet 5 (classic game loops,
well-trodden); chess → Opus 4.8 (minimax/eval correctness rewards deep
single-domain reasoning); roguelike → Fable 5 for the design-doc session,
then Sonnet 5 for the implementation sessions that follow the approved
design.

**Goal:** replace the open-source game packages (nethack, crawl, nsnake,
vitetris, ninvaders, gnuchess, 2048, nudoku) with in-house terminal games.
`system/etc/zenhub/recreation.toml` stays the registry — games are config
entries, not Hub code.

Build order (operator said fine to split across chats):
1. **zenarcade** — one program, several small games, shared engine
   (top-level `games/zenarcade/`): Snake, a falling-blocks game, 2048,
   Sudoku, and an Invaders-like. Shared: game loop w/ frame timing,
   input map, score persistence per user (their data dir), CRT theme.
   This alone retires nsnake/vitetris/ninvaders/2048/nudoku.
2. **Chess** — vs. a simple built-in AI (minimax + a small eval is fine;
   it's a terminal, not a rating ladder). Retires gnuchess.
3. **Roguelike** — the big one, its own project (`games/zendepths/` or a
   name the operator picks): procedural floors, turn-based, permadeath,
   Aperture/Vault flavor. Retires nethack/crawl. Expect multiple sessions;
   start with a design doc for the operator to approve.
4. As each lands: update recreation.toml defaults + `_DEFAULT` in
   `hub/zenhub/screens/recreation.py`, drop the replaced packages from
   packages.txt (`nethack` is currently the only one actually listed).

---

## Parked (not in this queue, decisions already recorded)

- **NETWORK ARCHIVE** (retrieval-terminal web area, Kagi or Brave search
  API) — post-v1, see OPEN-QUESTIONS.md §10.
- **User-ID provisioning system** (replaces setup code `1234`) — see
  docs/USERS.md.
- **Real per-account Linux sessions + quota enforcement** — TODO(hardware),
  see docs/USERS.md.
- **Quota amounts / tier names sign-off** — ⬜ in OPEN-QUESTIONS.md §10.
