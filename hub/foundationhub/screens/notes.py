"""Notes — the operator's writing space (spec §5, BUILD-QUEUE §1, feedback #8).

One home, reached from Programs, split by *purpose* into two sections on a
single page — **Work** first, **Personal** last. Each section has:

  * plain notes, named on creation (the `--- create new note ---` row), and
  * one dated feature: Work gets timestamped **Dated Entries** (several per
    day); Personal gets the one-page-per-day **Dated Journal**.

Each section is its own folder under the account's data dir (`work/`,
`personal/`), so the File Manager — rooted at the same dir — shows them as two
clean folders (feedback #8). Everything opens in the one in-house editor
(`foundationhub.editor`); rename lives in the editor, delete in the File
Manager. Search is a separate program (`NotesSearchScreen`).

NOT exempt from Frank — the spec dropped the exempt/private zone (§5, §9).
These are ordinary `.md` files under the operator's data dir; Frank's
filesystem watcher sees them like anything else.
"""
from __future__ import annotations

import datetime as _dt
import os
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


def _open_note(path: Path, *, title: str, create_text: str = "",
                title_for=None) -> EditorScreen:
    return EditorScreen(path, title=title, create_text=create_text,
                        title_for=title_for)


def _today_screen(section: str) -> EditorScreen:
    """Today's journal page for a section. The dated header is seeded in the
    buffer only — the file appears on disk when the operator saves, not before."""
    today = _dt.date.today().isoformat()
    path = notesdb.journal_dir(user_dir(), section) / f"{today}.md"
    return _open_note(path, title=f"{labels.NOTE_JOURNAL} — {today}",
                      create_text=f"# {today}\n\n",
                      title_for=lambda p: f"{labels.NOTE_JOURNAL} — {p.stem}")


def _new_dated_entry(section: str) -> EditorScreen:
    """A fresh dated entry (feedback #7), timestamped to the minute — unlike the
    journal's one-file-per-day, several can exist for the same day. Writes into
    the section's `dated/` subfolder."""
    now = _dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d-%H%M")   # sortable filename, unaffected by display format
    header = (f"{now.strftime('%A')} - {now.strftime('%m/%d/%Y')} - "
              f"{int(now.strftime('%I'))}:{now.strftime('%M')} - "
              f"{now.strftime('%p').lower()}")
    path = notesdb.dated_dir(user_dir(), section) / f"{stamp}.md"
    return _open_note(path, title=f"{labels.NOTES_DATED} — {header}",
                      create_text=f"# {header}\n\n",
                      title_for=lambda p: f"{labels.NOTES_DATED} — {p.stem}")


class _ListScreen(Screen):
    """Shared shape for the journal/dated browsers: a menu rebuilt from disk
    on every draw (draws only happen per keypress; a listdir is cheap and the
    list can never go stale after an editor pops)."""

    def __init__(self):
        self.menu = Menu([])
        self._names: tuple[str, ...] | None = None

    def _paths(self) -> list[Path]:  # override
        return []

    def _items(self, paths: list[Path]) -> list[MenuItem]:  # override
        return []

    def _refresh(self) -> None:
        paths = self._paths()
        names = tuple(p.name for p in paths)
        if names != self._names:
            self._names = names
            index = self.menu.index
            self.menu = Menu(self._items(paths))
            self.menu.index = min(index, max(0, len(self.menu.items) - 1))

    def draw(self, win, top, left):
        self._refresh()
        self.menu.draw(win, top, left)

    def handle_key(self, key, app):
        self._refresh()
        result = self.menu.handle_key(key, app)
        if result is not None:
            return result
        if key in KEYS_BACK:
            return POP
        return None


class JournalScreen(_ListScreen):
    """Personal DATED JOURNAL: one page per day. Today's page on top; if it
    already exists, selecting it says so and opens it rather than pretending
    it's new (feedback #8). Past pages follow, newest first."""

    title = labels.NOTE_JOURNAL
    subtitle = labels.NOTE_JOURNAL_SUBTITLE

    def __init__(self, section: str = notesdb.SECTION_PERSONAL):
        super().__init__()
        self.section = section

    def _paths(self) -> list[Path]:
        return notesdb.list_journal(user_dir(), self.section)

    def _items(self, paths: list[Path]) -> list[MenuItem]:
        today = _dt.date.today().isoformat()
        items = [MenuItem(labels.NOTE_TODAY, self._open_today, hint=today)]
        past = [p for p in paths if p.stem != today]
        if past:
            items.append(MenuItem("", enabled=False))
        for p in past:
            items.append(MenuItem(
                p.stem,
                lambda a, p=p: _open_note(
                    p, title=f"{labels.NOTE_JOURNAL} — {p.stem}",
                    title_for=lambda pp: f"{labels.NOTE_JOURNAL} — {pp.stem}"),
                hint=" ".join(f"#{t}" for t in notesdb.note_tags(p)[:4])))
        return items

    def _open_today(self, app):
        today = _dt.date.today().isoformat()
        path = notesdb.journal_dir(user_dir(), self.section) / f"{today}.md"
        if path.exists():
            app.status_message = labels.NOTE_TODAY_EXISTS
        return _today_screen(self.section)


class DatedAreaScreen(_ListScreen):
    """Work DATED ENTRIES (feedback #7): timestamped to the minute, so several
    entries can exist for the same day — unlike `JournalScreen`, which is one
    file per day. Reads/writes the section's `dated/` subfolder."""

    title = labels.NOTES_DATED
    subtitle = labels.NOTES_DATED_SUBTITLE

    def __init__(self, section: str = notesdb.SECTION_WORK):
        super().__init__()
        self.section = section

    def _paths(self) -> list[Path]:
        return notesdb.list_dated(user_dir(), self.section)

    def _items(self, paths: list[Path]) -> list[MenuItem]:
        items = [MenuItem(labels.NOTES_DATED_NEW,
                          lambda a: _new_dated_entry(self.section))]
        if not paths:
            items.append(MenuItem(labels.NOTES_DATED_EMPTY, enabled=False))
        else:
            items.append(MenuItem("", enabled=False))
        for p in paths:
            items.append(MenuItem(
                p.stem,
                lambda a, p=p: _open_note(
                    p, title=f"{labels.NOTES_DATED} — {p.stem}",
                    title_for=lambda pp: f"{labels.NOTES_DATED} — {pp.stem}"),
                hint=" ".join(f"#{t}" for t in notesdb.note_tags(p)[:4])))
        return items


class NotesScreen(Screen):
    """The one notes home (feedback #8): a single page with two purpose
    sections — Work first, Personal last, set apart by a blank gap. Each
    section pins `--- create new note ---` and its dated feature above the
    section's plain notes. `create new note` asks for a NAME, then drops into
    the editor (the file lands on SAVE, like every other note)."""

    title = labels.NOTES
    subtitle = labels.NOTES_SUBTITLE

    _LIST, _NEW = range(2)

    def __init__(self):
        notesdb.migrate_legacy(user_dir())
        self.menu = Menu([])
        self._sig: tuple | None = None
        self.mode = self._LIST
        self.edit = LineEdit(limit=48)
        self.message = ""
        self._new_section = notesdb.SECTION_WORK

    # ── item building ─────────────────────────────────────────────────────────
    def _section_rows(self, section: str, header: str,
                       dated_row: MenuItem) -> list[MenuItem]:
        rows = [
            MenuItem(f"— {header} —", enabled=False),
            MenuItem("", enabled=False),
            MenuItem(labels.NOTES_NEW,
                     lambda a, s=section: self._begin_new(s)),
            dated_row,
        ]
        paths = notesdb.list_notes(user_dir(), section)
        if not paths:
            rows.append(MenuItem(labels.NOTES_EMPTY, enabled=False))
        for p in paths:
            rows.append(MenuItem(
                p.stem,
                lambda a, p=p: _open_note(p, title=p.stem),
                hint=" ".join(f"#{t}" for t in notesdb.note_tags(p)[:4])))
        return rows

    def _build(self) -> list[MenuItem]:
        work_dated = MenuItem(labels.NOTES_DATED,
                              lambda a: DatedAreaScreen(notesdb.SECTION_WORK),
                              hint="timestamped, several per day")
        personal_journal = MenuItem(labels.NOTE_JOURNAL,
                                    lambda a: JournalScreen(notesdb.SECTION_PERSONAL),
                                    hint="one page per day")
        items = self._section_rows(notesdb.SECTION_WORK, labels.NOTES_WORK,
                                    work_dated)
        # Blank gap between the Work and Personal sections (operator ask).
        items.append(MenuItem("", enabled=False))
        items.append(MenuItem("", enabled=False))
        items += self._section_rows(notesdb.SECTION_PERSONAL, labels.NOTES_PERSONAL,
                                    personal_journal)
        return items

    def _signature(self) -> tuple:
        return (tuple(p.name for p in notesdb.list_notes(user_dir(),
                                                         notesdb.SECTION_WORK)),
                tuple(p.name for p in notesdb.list_notes(user_dir(),
                                                         notesdb.SECTION_PERSONAL)))

    def _refresh(self) -> None:
        sig = self._signature()
        if sig != self._sig:
            self._sig = sig
            index = self.menu.index
            self.menu = Menu(self._build())
            self.menu.set_index(index)

    # ── drawing ───────────────────────────────────────────────────────────────
    def draw(self, win, top, left):
        self._refresh()
        self.menu.draw(win, top, left)
        h, w = win.getmaxyx()
        row = h - 4
        if self.mode == self._NEW:
            win.addstr(row, left,
                       f"{labels.NOTES_NAME_PROMPT} {self.edit.display()}"
                       [: w - left - 2],
                       theme.attr(theme.PAIR_ACCENT, bold=True))
        elif self.message:
            win.addstr(row, left, self.message[: w - left - 2],
                       theme.attr(theme.PAIR_WARN, bold=True))

    def status_text(self):
        if self.mode == self._NEW:
            return labels.REG_HINT
        return labels.NOTES_HINT

    # ── input ─────────────────────────────────────────────────────────────────
    def handle_key(self, key, app):
        self.message = ""
        if self.mode == self._NEW:
            return self._handle_name(key)
        self._refresh()
        result = self.menu.handle_key(key, app)
        if result is not None:
            return result
        if key in KEYS_BACK:
            return POP
        return None

    def _begin_new(self, section: str):
        self._new_section = section
        self.mode = self._NEW
        self.edit = LineEdit(limit=48)
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
        target = notesdb.note_path(user_dir(), self._new_section, name)
        if target.exists():
            # Name collides with an existing note: open it rather than dead-end.
            return _open_note(target, title=target.stem)
        # New note: the seeded header lives in the buffer; SAVE creates the file.
        return _open_note(target, title=name, create_text=f"# {name}\n\n")


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
                     lambda a, h=hit: _open_note(h.path, title=h.path.stem),
                     hint=(f"[{hit.section}] {hit.snippet}")[:40])
            for hit in self.hits])
        if self.hits:
            self.mode = self._RESULTS
