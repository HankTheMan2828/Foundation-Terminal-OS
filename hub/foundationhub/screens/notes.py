"""Notes — the operator's writing space (spec §5, BUILD-QUEUE §1, feedback #8).

One home, reached from Programs. The old stacked two-section page was mush —
`create new note` and the dated feature both looked like notes and nobody could
tell where their notes actually were. This is the reworked layout (operator
whiteboard, 2026-07-09):

  * a **WORK | PERSONAL** tab at the top — one switch, one section shown at a
    time (`Tab` or `←/→` flips between them);
  * a single numbered **AVAILABLE NOTES** list for the current section, each row
    showing when the note was last edited (time · day · full date);
  * a one-line **command area** you drive by typing, then `↵`:
        <number>   open that note
        n          create a new (named) note
        j          open/create today's Journal page for this section
        x 2-4      delete notes 2 through 4   (also `x 2 5 7`) — asks to confirm
        q / Esc    leave Notes

Each section is its own folder under the account's data dir (`work/`,
`personal/`), so the File Manager — rooted at the same dir — shows them as two
clean folders. Journal pages live in each section's `journal/` subfolder (one
page per day) but still appear inline in the numbered list. Everything opens in
the one in-house editor (`foundationhub.editor`); rename lives in the editor.

NOT exempt from Frank — these are ordinary `.md` files under the operator's data
dir; Frank's filesystem watcher sees them like anything else.
"""
from __future__ import annotations

import curses
import datetime as _dt
import os
import re
from pathlib import Path

from .. import labels, notesdb, session, theme
from ..app import POP, Screen
from ..editor import EditorScreen
from ..ui import KEYS_BACK, KEYS_SELECT, LineEdit, Menu, MenuItem

DATA = Path(os.environ.get("FOUNDATIONHUB_DATA",
            os.path.expanduser("~/.local/share/foundationhub")))


def user_dir() -> Path:
    """Each logical account gets its own notes space (docs/USERS.md). On the
    target this will live inside the account's quota'd home; in the layered
    scaffold it's namespaced under the shared data dir."""
    acct = session.get_active_account()
    if acct is not None:
        return DATA / "users" / acct.username
    return DATA


# ── helpers shared by the screen ─────────────────────────────────────────────
def _stamp(path: Path) -> str:
    """The last-edited stamp shown on each row: `12:39  Tuesday  07/08/2026`
    (time · day · full date, per the whiteboard). Empty if the file is gone."""
    try:
        dt = _dt.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return ""
    return dt.strftime("%H:%M  %A  %m/%d/%Y")


def _title_of(path: Path) -> str:
    """Editor header for an opened note: journal pages keep a JOURNAL prefix so
    a dated stem doesn't read as a random note; plain notes use their name."""
    if notesdb.is_journal(path):
        return f"{labels.NOTE_JOURNAL} — {path.stem}"
    return path.stem


def _title_for(path: Path):
    """Recompute the header after an in-editor rename, mirroring `_title_of`."""
    if notesdb.is_journal(path):
        return f"{labels.NOTE_JOURNAL} — {path.stem}"
    return path.stem


def _open_note(path: Path, *, create_text: str = "") -> EditorScreen:
    return EditorScreen(path, title=_title_of(path), create_text=create_text,
                        title_for=_title_for)


def _add(win, y: int, x: int, text: str, attr: int) -> None:
    """addstr that swallows the edge-of-window curses error, like ui.py does."""
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def _parse_indices(spec: str) -> list[int]:
    """Turn a delete spec (`2-4`, `2 5 7`, `2-4,6`) into a list of 1-based note
    numbers. Ranges expand inclusively; junk tokens are ignored, never fatal."""
    out: list[int] = []
    for tok in re.split(r"[\s,]+", spec.strip()):
        if not tok:
            continue
        if "-" in tok:
            lo_s, _, hi_s = tok.partition("-")
            if lo_s.isdigit() and hi_s.isdigit():
                lo, hi = int(lo_s), int(hi_s)
                if lo > hi:
                    lo, hi = hi, lo
                out.extend(range(lo, hi + 1))
        elif tok.isdigit():
            out.append(int(tok))
    return out


class NotesScreen(Screen):
    """The one notes home: a WORK | PERSONAL tab over a single numbered list,
    driven by a typed command line (open by number, `n` new, `j` journal,
    `x` delete, `q`/Esc quit). See the module docstring for the full grammar."""

    title = labels.NOTES
    subtitle = labels.NOTES_SUBTITLE

    _LIST, _NEW, _CONFIRM = range(3)

    def __init__(self):
        notesdb.migrate_legacy(user_dir())
        self.section = notesdb.SECTION_WORK
        self.paths: list[Path] = []       # current section, as last drawn
        self.mode = self._LIST
        self.cmd = LineEdit(limit=32)     # the command line (LIST mode)
        self.edit = LineEdit(limit=48)    # the new-note name (NEW mode)
        self.pending: list[Path] = []     # notes awaiting a delete confirm
        self.message = ""
        self._scroll = 0                  # first visible row when the list overflows

    # ── data ────────────────────────────────────────────────────────────────
    def _refresh(self) -> None:
        """Rebuild the visible list from disk. Cheap (a scandir), and drawing
        only happens per keypress, so the numbers can never go stale."""
        self.paths = notesdb.list_all(user_dir(), self.section)

    def _toggle_section(self) -> None:
        self.section = (notesdb.SECTION_PERSONAL
                        if self.section == notesdb.SECTION_WORK
                        else notesdb.SECTION_WORK)
        self._scroll = 0
        self.message = ""
        self.cmd = LineEdit(limit=32)

    # ── drawing ───────────────────────────────────────────────────────────────
    def draw(self, win, top, left):
        self._refresh()
        h, w = win.getmaxyx()
        width = max(0, w - 2 * left)
        cmd_row = h - 3
        msg_row = h - 4
        self._draw_tabs(win, top, left, width)
        _add(win, top + 2, left, labels.NOTES_AVAILABLE,
             theme.attr(theme.PAIR_AMBER, bold=True))
        self._draw_list(win, top + 3, left, width, msg_row - 2)
        self._draw_prompt(win, msg_row, cmd_row, left, width)

    def _draw_tabs(self, win, top, left, width):
        x = left
        for idx, (sec, lbl) in enumerate(
                ((notesdb.SECTION_WORK, labels.NOTES_WORK),
                 (notesdb.SECTION_PERSONAL, labels.NOTES_PERSONAL))):
            if idx:
                _add(win, top, x, "  |  ", theme.attr(theme.PAIR_DIM, dim=True))
                x += 5
            if sec == self.section:
                _add(win, top, x, f"[ {lbl} ]",
                     theme.attr(theme.PAIR_HILITE, bold=True))
            else:
                _add(win, top, x, f"  {lbl}  ",
                     theme.attr(theme.PAIR_DIM, dim=True))
            x += len(lbl) + 4
        hint = labels.NOTES_TAB_HINT
        _add(win, top, left + max(0, width - len(hint)), hint,
             theme.attr(theme.PAIR_DIM, dim=True))

    def _draw_list(self, win, y0, left, width, y_bottom):
        if not self.paths:
            _add(win, y0, left, labels.NOTES_EMPTY,
                 theme.attr(theme.PAIR_DIM, dim=True))
            return
        rows = max(1, y_bottom - y0 + 1)
        self._scroll = max(0, min(self._scroll, len(self.paths) - rows))
        if self._scroll < 0:
            self._scroll = 0
        visible = self.paths[self._scroll: self._scroll + rows]
        for i, p in enumerate(visible):
            n = self._scroll + i + 1
            title = p.stem
            if notesdb.is_journal(p):
                title = f"{title}  {labels.NOTE_JOURNAL_TAG}"
            head = f"[{n:>2}] {title}"
            stamp = _stamp(p)
            gap = max(2, width - len(head) - len(stamp))
            line = (head + " " * gap + stamp)[:width]
            _add(win, y0 + i, left, line, theme.attr(theme.PAIR_NORMAL))

    def _draw_prompt(self, win, msg_row, cmd_row, left, width):
        if self.mode == self._NEW:
            _add(win, cmd_row, left,
                 f"{labels.NOTES_NAME_PROMPT} {self.edit.display()}"[:width],
                 theme.attr(theme.PAIR_ACCENT, bold=True))
            return
        if self.mode == self._CONFIRM:
            names = ", ".join(f"[{self.paths.index(p) + 1}] {p.stem}"
                              for p in self.pending if p in self.paths)
            _add(win, msg_row, left, f"delete: {names}"[:width],
                 theme.attr(theme.PAIR_WARN))
            _add(win, cmd_row, left,
                 labels.NOTES_DELETE_CONFIRM.format(n=len(self.pending)),
                 theme.attr(theme.PAIR_WARN, bold=True))
            return
        if self.message:
            _add(win, msg_row, left, self.message[:width],
                 theme.attr(theme.PAIR_WARN, bold=True))
        _add(win, cmd_row, left,
             f"{labels.NOTES_CMD_PROMPT} {self.cmd.display()}"[:width],
             theme.attr(theme.PAIR_ACCENT, bold=True))

    def status_text(self):
        if self.mode == self._NEW:
            return labels.REG_HINT
        if self.mode == self._CONFIRM:
            return labels.REG_HINT
        return labels.NOTES_HINT

    # ── input ─────────────────────────────────────────────────────────────────
    def handle_key(self, key, app):
        self.message = ""
        if self.mode == self._CONFIRM:
            return self._handle_confirm(key)
        if self.mode == self._NEW:
            return self._handle_name(key)
        # LIST mode — the command line, plus live tab/scroll keys.
        if key == ord("\t") or key in (curses.KEY_LEFT, curses.KEY_RIGHT):
            self._toggle_section()
            return None
        if key == curses.KEY_UP:
            self._scroll = max(0, self._scroll - 1)
            return None
        if key == curses.KEY_DOWN:
            self._scroll += 1     # clamped against the list length on next draw
            return None
        result = self.cmd.handle(key)
        if result == "cancel":    # Esc — leave Notes (whiteboard: same as q)
            return POP
        if result == "submit":
            return self._run_command()
        return None

    def _run_command(self):
        raw = self.cmd.value.strip()
        self.cmd = LineEdit(limit=32)
        if not raw:
            return None
        low = raw.lower()
        if low in ("q", "quit"):
            return POP
        if low in ("n", "new"):
            self.mode = self._NEW
            self.edit = LineEdit(limit=48)
            return None
        if low in ("j", "journal"):
            return self._open_journal()
        if low[0] == "x":
            return self._begin_delete(raw[1:])
        if low.isdigit():
            return self._open_number(int(low))
        self.message = labels.NOTES_UNKNOWN
        return None

    def _open_number(self, n: int):
        if 1 <= n <= len(self.paths):
            return _open_note(self.paths[n - 1])
        self.message = labels.NOTES_NO_SUCH.format(n=n)
        return None

    def _open_journal(self):
        today = _dt.date.today().isoformat()
        path = notesdb.journal_path(user_dir(), self.section, today)
        if path.exists():
            return _open_note(path)
        return _open_note(path, create_text=f"# {today}\n\n")

    def _begin_delete(self, spec: str):
        wanted: list[Path] = []
        for n in _parse_indices(spec):
            if 1 <= n <= len(self.paths):
                p = self.paths[n - 1]
                if p not in wanted:
                    wanted.append(p)
        if not wanted:
            self.message = labels.NOTES_DELETE_NONE
            return None
        self.pending = wanted
        self.mode = self._CONFIRM
        return None

    def _handle_confirm(self, key):
        if key in (ord("y"), ord("Y")):
            count = 0
            for p in self.pending:
                try:
                    p.unlink()
                    count += 1
                except OSError:
                    pass
            self.message = labels.NOTES_DELETED.format(n=count)
        # Anything else (n / Esc / Backspace / stray key) cancels — the safe default.
        self.pending = []
        self.mode = self._LIST
        return None

    def _handle_name(self, key):
        result = self.edit.handle(key)
        if result == "cancel":
            self.mode = self._LIST
            return None
        if result != "submit":
            return None
        name = self.edit.value.strip()
        self.mode = self._LIST
        if not name:
            return None
        target = notesdb.note_path(user_dir(), self.section, name)
        if target.exists():
            # Name collides with an existing note: open it rather than dead-end.
            return _open_note(target)
        # New note: the seeded header lives in the buffer; SAVE creates the file.
        return _open_note(target, create_text=f"# {name}\n\n")


class NotesSearchScreen(Screen):
    """NOTES SEARCH (separate program, feedback #8): free text and #tags,
    AND-matched. First asks whether to include Personal notes — default NO, so
    a plain search only touches Work."""

    title = labels.NOTES_SEARCH
    subtitle = labels.NOTES_SEARCH_SUBTITLE

    _ASK, _INPUT, _RESULTS = range(3)

    def __init__(self):
        notesdb.migrate_legacy(user_dir())
        self.mode = self._ASK
        self.include_personal = False
        self.edit = LineEdit(limit=64)
        self.hits: list[notesdb.Hit] = []
        self.menu = Menu([])
        self.searched = False

    def _sections(self) -> tuple[str, ...]:
        return notesdb.SECTIONS if self.include_personal else (notesdb.SECTION_WORK,)

    def draw(self, win, top, left):
        h, w = win.getmaxyx()
        if self.mode == self._ASK:
            win.addstr(top, left, labels.NOTES_SEARCH_ASK,
                       theme.attr(theme.PAIR_ACCENT, bold=True))
            return
        scope = "work + personal" if self.include_personal else "work only"
        win.addstr(top, left, f"{labels.SEARCH_PROMPT}   [{scope}]:",
                   theme.attr(theme.PAIR_DIM, dim=True))
        win.addstr(top + 1, left, self.edit.display()[: w - left - 2],
                   theme.attr(theme.PAIR_NORMAL, bold=True))
        if self.searched and not self.hits:
            win.addstr(top + 3, left, labels.SEARCH_NONE,
                       theme.attr(theme.PAIR_WARN, bold=True))
        elif self.hits:
            self.menu.draw(win, top + 3, left)

    def status_text(self):
        if self.mode == self._ASK:
            return "y include personal   n/↵ work only   Esc back"
        if self.mode == self._RESULTS:
            return f"{labels.SEARCH_RESULTS_HINT}   ({len(self.hits)} found)"
        return labels.SEARCH_HINT

    def handle_key(self, key, app):
        if self.mode == self._ASK:
            if key in (ord("y"), ord("Y")):
                self.include_personal = True
                self.mode = self._INPUT
            elif key in (ord("n"), ord("N")) or key in KEYS_SELECT:
                self.include_personal = False
                self.mode = self._INPUT
            elif key in KEYS_BACK:
                return POP
            return None
        if self.mode == self._RESULTS:
            if key == 27:               # Esc: back to the query line
                self.mode = self._INPUT
                return None
            result = self.menu.handle_key(key, app)
            if result is not None:
                return result
            if key in KEYS_BACK:
                self.mode = self._INPUT
            return None
        result = self.edit.handle(key)
        if result == "cancel":
            return POP
        if result == "submit":
            self._run_search()
        return None

    def _run_search(self) -> None:
        self.hits = notesdb.search(user_dir(), self.edit.value, self._sections())
        self.searched = True
        self.menu = Menu([
            MenuItem(hit.path.stem,
                     lambda a, h=hit: _open_note(h.path),
                     hint=(f"[{hit.section}] {hit.snippet}")[:40])
            for hit in self.hits])
        if self.hits:
            self.mode = self._RESULTS
