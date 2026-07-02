"""Personal File — the operator's own space (spec §5, BUILD-QUEUE §1).

The full in-house notes suite: a dated journal, tagged notes, and search,
all inside the Hub, all opening in the in-house editor (`foundationhub.editor`).
No external editor, ever — the EDITOR env fallback and the ranger launch
are gone with it.

NOT exempt from Frank — the spec explicitly dropped an exempt/private zone
(§5, §9). These are ordinary `.md` files under the operator's data dir;
Frank's filesystem watcher sees them like anything else.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .. import labels, notesdb, session, theme
from ..app import MenuScreen, Screen, POP
from ..editor import EditorScreen
from ..ui import KEYS_BACK, LineEdit, Menu, MenuItem

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


def _open_note(path: Path, *, title: str, create_text: str = "") -> EditorScreen:
    return EditorScreen(path, title=title, create_text=create_text)


def _today_screen() -> EditorScreen:
    """Today's journal entry. The dated header is seeded in the buffer only —
    the file appears on disk when the operator saves, not before."""
    today = _dt.date.today().isoformat()
    path = user_dir() / notesdb.JOURNAL_DIR / f"{today}.md"
    return _open_note(path, title=f"{labels.NOTE_JOURNAL} — {today}",
                      create_text=f"# {today}\n\n")


class _ListScreen(Screen):
    """Shared shape for the journal/notes browsers: a menu rebuilt from disk
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
    """DATED JOURNAL: today's entry on top, then past entries, newest first."""

    title = labels.NOTE_JOURNAL
    subtitle = "one page per day — the record keeps itself"

    def _paths(self) -> list[Path]:
        return notesdb.list_journal(user_dir())

    def _items(self, paths: list[Path]) -> list[MenuItem]:
        today = _dt.date.today().isoformat()
        items = [MenuItem(labels.NOTE_TODAY, lambda a: _today_screen(),
                          hint=today)]
        past = [p for p in paths if p.stem != today]
        if past:
            items.append(MenuItem("", enabled=False))
        for p in past:
            items.append(MenuItem(
                p.stem,
                lambda a, p=p: _open_note(
                    p, title=f"{labels.NOTE_JOURNAL} — {p.stem}"),
                hint=" ".join(f"#{t}" for t in notesdb.note_tags(p)[:4])))
        return items


class TaggedNotesScreen(_ListScreen):
    """TAGGED NOTES: native list of notes/*.md — create, rename, delete,
    open in the editor. Replaces the old ranger launch."""

    title = labels.NOTE_TAGGED
    subtitle = "inline #tags file these for you"

    _LIST, _NEW, _RENAME, _DELETE = range(4)

    def __init__(self):
        super().__init__()
        self.mode = self._LIST
        self.edit = LineEdit(limit=48)
        self.message = ""

    def _dir(self) -> Path:
        return user_dir() / notesdb.NOTES_DIR

    def _paths(self) -> list[Path]:
        return notesdb.list_notes(user_dir())

    def _items(self, paths: list[Path]) -> list[MenuItem]:
        if not paths:
            return [MenuItem(labels.NOTE_EMPTY, enabled=False)]
        return [MenuItem(
                    p.stem,
                    lambda a, p=p: _open_note(p, title=p.stem),
                    hint=" ".join(f"#{t}" for t in notesdb.note_tags(p)[:4]))
                for p in paths]

    def _selected_path(self) -> Path | None:
        item = self.menu.current
        if item is None or not item.enabled:
            return None
        return self._dir() / f"{item.label}.md"

    # ── drawing ──────────────────────────────────────────────────────────────
    def draw(self, win, top, left):
        self._refresh()
        self.menu.draw(win, top, left)
        h, w = win.getmaxyx()
        row = h - 4
        if self.mode in (self._NEW, self._RENAME):
            prompt = (labels.NOTE_NAME_PROMPT if self.mode == self._NEW
                      else labels.NOTE_RENAME_PROMPT)
            win.addstr(row, left, f"{prompt}: {self.edit.display()}"[: w - left - 2],
                       theme.attr(theme.PAIR_ACCENT, bold=True))
        elif self.mode == self._DELETE:
            target = self.menu.current.label if self.menu.current else ""
            win.addstr(row, left,
                       labels.NOTE_DELETE_CONFIRM.format(name=target)[: w - left - 2],
                       theme.attr(theme.PAIR_WARN, bold=True))
        elif self.message:
            win.addstr(row, left, self.message[: w - left - 2],
                       theme.attr(theme.PAIR_WARN, bold=True))

    def status_text(self):
        if self.mode in (self._NEW, self._RENAME):
            return labels.REG_HINT
        return labels.NOTES_HINT

    # ── input ────────────────────────────────────────────────────────────────
    def handle_key(self, key, app):
        self.message = ""
        if self.mode == self._NEW:
            return self._handle_name(key, rename=False)
        if self.mode == self._RENAME:
            return self._handle_name(key, rename=True)
        if self.mode == self._DELETE:
            return self._handle_delete(key)
        self._refresh()          # act on the current disk state, not a stale list
        if key == ord("n"):
            self.mode = self._NEW
            self.edit = LineEdit(limit=48)
            return None
        if key == ord("r") and self._selected_path() is not None:
            self.mode = self._RENAME
            sel = self.menu.current
            self.edit = LineEdit(limit=48, value=sel.label if sel else "")
            return None
        if key == ord("d") and self._selected_path() is not None:
            self.mode = self._DELETE
            return None
        return super().handle_key(key, app)

    def _handle_name(self, key, *, rename: bool):
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
        slug = notesdb.slugify(name)
        target = self._dir() / f"{slug}.md"
        if target.exists():
            self.message = labels.NOTE_EXISTS
            return None
        if rename:
            src = self._selected_path()
            if src is None or not src.exists():
                return None
            self._dir().mkdir(parents=True, exist_ok=True)
            src.rename(target)
            self._names = None      # force list rebuild
            return None
        # New note: seeded header lives in the buffer; SAVE creates the file.
        return _open_note(target, title=slug, create_text=f"# {name}\n\n")

    def _handle_delete(self, key):
        self.mode = self._LIST
        if key in (ord("y"), ord("Y")):
            path = self._selected_path()
            if path is not None:
                try:
                    path.unlink()
                    self.message = labels.NOTE_DELETED
                    self._names = None
                except OSError as exc:
                    self.message = str(exc)
        return None


class SearchScreen(Screen):
    """SEARCH: free text and #tags, AND-matched across journal + notes."""

    title = labels.NOTE_SEARCH
    subtitle = "words match text, #tags match tags"

    _INPUT, _RESULTS = range(2)

    def __init__(self):
        self.mode = self._INPUT
        self.edit = LineEdit(limit=64)
        self.hits: list[notesdb.Hit] = []
        self.menu = Menu([])
        self.searched = False

    def draw(self, win, top, left):
        h, w = win.getmaxyx()
        win.addstr(top, left, f"{labels.SEARCH_PROMPT}:",
                   theme.attr(theme.PAIR_DIM, dim=True))
        win.addstr(top + 1, left, self.edit.display()[: w - left - 2],
                   theme.attr(theme.PAIR_NORMAL, bold=True))
        if self.searched and not self.hits:
            win.addstr(top + 3, left, labels.SEARCH_NONE,
                       theme.attr(theme.PAIR_WARN, bold=True))
        elif self.hits:
            self.menu.draw(win, top + 3, left)

    def status_text(self):
        if self.mode == self._RESULTS:
            return f"{labels.SEARCH_RESULTS_HINT}   ({len(self.hits)} found)"
        return labels.SEARCH_HINT

    def handle_key(self, key, app):
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
        self.hits = notesdb.search(user_dir(), self.edit.value)
        self.searched = True
        self.menu = Menu([
            MenuItem(hit.path.stem,
                     lambda a, h=hit: _open_note(h.path, title=h.path.stem),
                     hint=hit.snippet[:40])
            for hit in self.hits])
        if self.hits:
            self.mode = self._RESULTS


def screen():
    items = [
        MenuItem(labels.NOTE_JOURNAL, lambda a: JournalScreen(),
                 hint="today, dated"),
        MenuItem(labels.NOTE_TAGGED, lambda a: TaggedNotesScreen(),
                 hint="notes with #tags"),
        MenuItem(labels.NOTE_SEARCH, lambda a: SearchScreen(),
                 hint="by tag and text"),
    ]
    return MenuScreen(labels.NOTES, items,
                      subtitle="not exempt from the overseer (§5)")
