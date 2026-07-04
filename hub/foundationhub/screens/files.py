"""FILE MANAGER (native Hub screen, BUILD-QUEUE §2). Retires ranger.

Scoped to the account's own data space (the same tree `notes.py` writes
into) — never a system-wide browser. Every navigation and destination path
goes through `fileops.enforce_scope`, so there is no way to walk above the
account's root via '..' or a symlink. Text files open in the shared editor
widget (`foundationhub.editor`) — the one-editor policy from §1 applies here too.
"""
from __future__ import annotations

from pathlib import Path

from .. import fileops, labels, session, theme
from ..app import POP, Screen
from ..editor import EditorScreen
from ..ui import KEYS_BACK, LineEdit, Menu, MenuItem
from .notes import user_dir


class FileManagerScreen(Screen):
    title = labels.PROG_FILES

    _LIST, _NEW, _RENAME, _DELETE = range(4)

    def __init__(self):
        root = user_dir()
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()
        self.cwd = self.root
        self.mode = self._LIST
        self.edit = LineEdit(limit=64)
        self.message = ""
        self.clip: tuple[Path, str] | None = None   # (path, "copy" | "cut")
        self.menu = Menu([])
        self._key = None
        self._refresh()

    # ── header: quota readout + current path (spec: "the visible face of
    # the fixed-allotment rule") ─────────────────────────────────────────────
    @property
    def subtitle(self) -> str:
        where = fileops.rel_path(self.root, self.cwd)
        acct = session.get_active_account()
        if acct is None:
            return where
        used = fileops.format_size(fileops.dir_size(self.root))
        quota = fileops.format_size(acct.info.quota_bytes)
        return f"{used} / {quota}   {where}"

    # ── listing (rebuilt from disk whenever the directory contents or cwd
    # change — draws only happen per keypress, so a listdir is cheap) ────────
    def _refresh(self) -> None:
        entries = fileops.list_dir(self.cwd)
        key = (self.cwd, tuple((e.path.name, e.is_dir, e.size, e.mtime)
                                for e in entries))
        if key != self._key:
            self._key = key
            index = self.menu.index
            self.menu = Menu(self._items(entries))
            self.menu.set_index(index)

    def _items(self, entries: list[fileops.Entry]) -> list[MenuItem]:
        items = []
        if self.cwd != self.root:
            items.append(MenuItem(labels.FILES_UP, lambda a: self._go_up()))
        if not entries:
            items.append(MenuItem(labels.FILES_EMPTY, enabled=False))
        for e in entries:
            if e.is_dir:
                items.append(MenuItem(e.path.name,
                                       lambda a, p=e.path: self._enter(p),
                                       hint="DIR"))
            else:
                items.append(MenuItem(e.path.name,
                                       lambda a, p=e.path: self._open(p),
                                       hint=fileops.format_size(e.size)))
        return items

    def _selected_path(self) -> Path | None:
        item = self.menu.current
        if item is None or not item.enabled or item.label == labels.FILES_UP:
            return None
        return self.cwd / item.label

    # ── navigation ───────────────────────────────────────────────────────────
    def _enter(self, path: Path):
        self.cwd = fileops.enforce_scope(self.root, path)
        self._key = None
        return None

    def _go_up(self):
        if self.cwd != self.root:
            self.cwd = fileops.enforce_scope(self.root, self.cwd.parent)
            self._key = None
        return None

    def _open(self, path: Path):
        if fileops.is_text_file(path):
            return EditorScreen(path, title=path.name)
        self.message = labels.FILES_CANNOT_OPEN
        return None

    def _paste(self) -> None:
        if self.clip is None:
            self.message = labels.FILES_NOTHING_MARKED
            return
        src, kind = self.clip
        try:
            fileops.enforce_scope(self.root, src)
            if kind == "copy":
                fileops.do_copy(src, self.cwd)
            else:
                fileops.do_move(src, self.cwd)
                self.clip = None
            self.message = labels.FILES_PASTED
            self._key = None
        except fileops.NameExists:
            self.message = labels.FILES_EXISTS
        except (fileops.ScopeError, fileops.FileOpError, OSError) as exc:
            self.message = str(exc)

    # ── drawing ──────────────────────────────────────────────────────────────
    def draw(self, win, top, left):
        self._refresh()
        self.menu.draw(win, top, left)
        h, w = win.getmaxyx()
        row = h - 4
        if self.mode in (self._NEW, self._RENAME):
            prompt = (labels.FILES_NAME_PROMPT if self.mode == self._NEW
                      else labels.FILES_RENAME_PROMPT)
            win.addstr(row, left, f"{prompt}: {self.edit.display()}"[: w - left - 2],
                       theme.attr(theme.PAIR_ACCENT, bold=True))
        elif self.mode == self._DELETE:
            target = self.menu.current.label if self.menu.current else ""
            win.addstr(row, left,
                       labels.FILES_DELETE_CONFIRM.format(name=target)[: w - left - 2],
                       theme.attr(theme.PAIR_WARN, bold=True))
        elif self.message:
            win.addstr(row, left, self.message[: w - left - 2],
                       theme.attr(theme.PAIR_WARN, bold=True))

    def status_text(self):
        if self.mode in (self._NEW, self._RENAME):
            return labels.REG_HINT
        return labels.FILES_HINT

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
        sel = self._selected_path()
        if key == ord("n"):
            self.mode = self._NEW
            self.edit = LineEdit(limit=64)
            return None
        if key == ord("r") and sel is not None:
            self.mode = self._RENAME
            self.edit = LineEdit(limit=64, value=sel.name)
            return None
        if key == ord("d") and sel is not None:
            self.mode = self._DELETE
            return None
        if key == ord("c") and sel is not None:
            self.clip = (sel, "copy")
            self.message = labels.FILES_MARKED_COPY.format(name=sel.name)
            return None
        if key == ord("x") and sel is not None:
            self.clip = (sel, "cut")
            self.message = labels.FILES_MARKED_CUT.format(name=sel.name)
            return None
        if key == ord("v"):
            self._paste()
            return None
        if key in KEYS_BACK:
            return self._go_up() if self.cwd != self.root else POP
        return self.menu.handle_key(key, app)

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
        try:
            if rename:
                sel = self._selected_path()
                if sel is None:
                    return None
                fileops.do_rename(sel, name)
            else:
                fileops.do_new_dir(self.cwd, name)
            self._key = None
        except fileops.NameExists:
            self.message = labels.FILES_EXISTS
        except fileops.InvalidName:
            self.message = labels.FILES_INVALID_NAME
        return None

    def _handle_delete(self, key):
        self.mode = self._LIST
        if key in (ord("y"), ord("Y")):
            sel = self._selected_path()
            if sel is not None:
                try:
                    fileops.do_delete(sel)
                    self.message = labels.FILES_DELETED
                    self._key = None
                except OSError as exc:
                    self.message = str(exc)
        return None


def screen():
    return FileManagerScreen()
