"""THE system text editor (BUILD-QUEUE §1) — in-house, pure stdlib.

Three layers, so the logic stays testable and the widget stays reusable:

  Buffer        plain text-editing state machine — no curses, unit-tested.
  Editor        a curses *widget* (draw + handle_key), not a screen: the file
                manager and anything else that edits text composes this same
                widget. One-editor policy: there is no other editor, ever.
  EditorScreen  thin Screen wrapper so screens can just push an editor.

Keys: type to insert; arrows / Home / End / PgUp / PgDn move (hjkl are letters
here, so they type — vim keys stay for menus and lists, where they're sane);
Esc opens the SAVE / DISCARD / RETURN menu. The status line shows the file,
cursor position, and a dirty marker.
"""
from __future__ import annotations

import curses
from pathlib import Path

from . import activity, labels, notesdb, session, theme
from .app import POP, Screen
from .ui import KEYS_DOWN, KEYS_SELECT, KEYS_UP, LineEdit

TAB_SPACES = "    "


def wrap_segments(line: str, width: int) -> list[str]:
    """Hard-wrap one buffer line into display rows of at most `width` cells.
    Character wrap (not word wrap) keeps the cursor math exact."""
    if width <= 0 or not line:
        return [line]
    return [line[i:i + width] for i in range(0, len(line), width)]


class Buffer:
    """Line buffer + cursor. All edits set the dirty flag; no curses in here."""

    def __init__(self, text: str = ""):
        self.lines: list[str] = text.split("\n") if text else [""]
        self.row = 0
        self.col = 0
        self.dirty = False

    # ── contents ──────────────────────────────────────────────────────────────
    @property
    def line(self) -> str:
        return self.lines[self.row]

    def text(self) -> str:
        return "\n".join(self.lines)

    def _clamp_col(self) -> None:
        self.col = min(self.col, len(self.line))

    # ── movement ──────────────────────────────────────────────────────────────
    def move_up(self) -> None:
        if self.row > 0:
            self.row -= 1
            self._clamp_col()

    def move_down(self) -> None:
        if self.row < len(self.lines) - 1:
            self.row += 1
            self._clamp_col()

    def move_left(self) -> None:
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = len(self.line)

    def move_right(self) -> None:
        if self.col < len(self.line):
            self.col += 1
        elif self.row < len(self.lines) - 1:
            self.row += 1
            self.col = 0

    def move_home(self) -> None:
        self.col = 0

    def move_end(self) -> None:
        self.col = len(self.line)

    def move_page(self, delta_rows: int) -> None:
        self.row = max(0, min(len(self.lines) - 1, self.row + delta_rows))
        self._clamp_col()

    # ── edits ─────────────────────────────────────────────────────────────────
    def insert(self, s: str) -> None:
        """Insert printable text (no newlines — use newline()) at the cursor."""
        line = self.line
        self.lines[self.row] = line[: self.col] + s + line[self.col:]
        self.col += len(s)
        self.dirty = True

    def newline(self) -> None:
        line = self.line
        self.lines[self.row: self.row + 1] = [line[: self.col], line[self.col:]]
        self.row += 1
        self.col = 0
        self.dirty = True

    def backspace(self) -> None:
        if self.col > 0:
            line = self.line
            self.lines[self.row] = line[: self.col - 1] + line[self.col:]
            self.col -= 1
            self.dirty = True
        elif self.row > 0:
            prev = self.lines[self.row - 1]
            self.col = len(prev)
            self.lines[self.row - 1] = prev + self.line
            del self.lines[self.row]
            self.row -= 1
            self.dirty = True

    def delete(self) -> None:
        line = self.line
        if self.col < len(line):
            self.lines[self.row] = line[: self.col] + line[self.col + 1:]
            self.dirty = True
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] = line + self.lines[self.row + 1]
            del self.lines[self.row + 1]
            self.dirty = True


class Editor:
    """Curses widget around a Buffer: rendering, scrolling, the Esc menu.

    `handle_key` returns "close" when the operator saved or discarded their
    way out; the composing screen decides what "close" means (usually POP).
    """

    _MENU = (labels.EDITOR_MENU_SAVE, labels.EDITOR_MENU_RENAME,
             labels.EDITOR_MENU_DISCARD, labels.EDITOR_MENU_RETURN)

    def __init__(self, path: Path, *, create_text: str = "", wrap: bool = True):
        self.path = Path(path)
        self.wrap = wrap
        self.menu_open = False
        self.menu_index = 0
        self.rename_mode = False
        self.rename_edit = LineEdit(limit=48)
        self.message = ""
        self._top = 0        # first buffer line on screen
        self._left = 0       # horizontal scroll (no-wrap mode only)
        self._page = 20      # rows last drawn, for PgUp/PgDn
        try:
            self.buffer = Buffer(self.path.read_text(encoding="utf-8"))
        except OSError:
            # New file: seeded text exists only in the buffer until SAVE —
            # discarding an untouched new note leaves no file behind.
            self.buffer = Buffer(create_text)
            if create_text:
                self.buffer.dirty = True
        # The note/file the user opened for editing — reported to Frank
        # (report-only; see activity.py).
        activity.record("note-open", self.path.name)

    # ── persistence ───────────────────────────────────────────────────────────
    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.buffer.text(), encoding="utf-8")
        except OSError as exc:
            self.message = labels.EDITOR_SAVE_FAILED.format(err=exc)
            return False
        self.buffer.dirty = False
        # Remember this path so a subsequent lockout can redact the matched
        # infraction text in the source file (same-length * per character).
        session.note_content_path(self.path)
        # Report the edit *with its content* so Frank's content-review tiers can
        # actually see what was written — this is the "notes edited" half of the
        # OG design (report-only; see activity.py).
        activity.record("note-save", f"{self.path.name}\n{self.buffer.text()}")
        return True

    # ── geometry ──────────────────────────────────────────────────────────────
    def _cursor_cell(self, width: int) -> tuple[int, int]:
        """Cursor position as (segment index within its line, x)."""
        if not self.wrap or width <= 0:
            return 0, self.buffer.col
        seg, x = divmod(self.buffer.col, width)
        if seg > 0 and x == 0 and self.buffer.col == len(self.buffer.line):
            seg, x = seg - 1, width   # EOL on an exact wrap boundary
        return seg, x

    def _line_rows(self, row: int, width: int) -> int:
        return len(wrap_segments(self.buffer.lines[row], width)) if self.wrap else 1

    def _scroll_to_cursor(self, height: int, width: int) -> None:
        buf = self.buffer
        if buf.row < self._top:
            self._top = buf.row
        if self.wrap:
            seg, _ = self._cursor_cell(width)
            rows = sum(self._line_rows(r, width)
                       for r in range(self._top, buf.row)) + seg + 1
            while rows > height and self._top < buf.row:
                rows -= self._line_rows(self._top, width)
                self._top += 1
        else:
            if buf.row >= self._top + height:
                self._top = buf.row - height + 1
            if buf.col < self._left:
                self._left = buf.col
            if buf.col >= self._left + width:
                self._left = buf.col - width + 1

    # ── drawing ───────────────────────────────────────────────────────────────
    def draw(self, win, top: int, left: int) -> None:
        h, w = win.getmaxyx()
        width = max(1, w - 2 * left)
        height = max(1, h - top - 2)
        self._page = height
        self._scroll_to_cursor(height, width)

        body = theme.attr(theme.PAIR_NORMAL)
        y = top
        row = self._top
        cursor_yx = None
        while y < top + height and row < len(self.buffer.lines):
            line = self.buffer.lines[row]
            segs = (wrap_segments(line, width) if self.wrap
                    else [line[self._left: self._left + width]])
            for i, seg in enumerate(segs):
                if y >= top + height:
                    break
                try:
                    win.addstr(y, left, seg[:width], body)
                except curses.error:
                    pass
                if row == self.buffer.row:
                    cseg, cx = self._cursor_cell(width)
                    if not self.wrap:
                        cx -= self._left
                    if i == cseg and 0 <= cx <= width:
                        cursor_yx = (y, left + cx, seg[cx] if cx < len(seg) else " ")
                y += 1
            row += 1

        if cursor_yx and not self.menu_open:
            cy, cx, ch = cursor_yx
            try:
                win.addstr(cy, cx, ch, theme.attr(theme.PAIR_HILITE, bold=True))
            except curses.error:
                pass

        if self.menu_open:
            self._draw_menu(win, top, left)
        elif self.rename_mode:
            self._draw_rename(win, left)

    def _draw_rename(self, win, left: int) -> None:
        h, w = win.getmaxyx()
        row = h - 4        # above the statusbar (drawn at h - 2 by draw_statusbar)
        prompt = f"{labels.EDITOR_RENAME_PROMPT}: {self.rename_edit.display()}"
        try:
            win.addstr(row, left, prompt[: w - left - 2],
                       theme.attr(theme.PAIR_ACCENT, bold=True))
        except curses.error:
            pass

    def _draw_menu(self, win, top: int, left: int) -> None:
        _, w = win.getmaxyx()
        width = max(0, w - 2 * left)  # match ui.Menu.draw's full-width highlight bar
        for i, label in enumerate(self._MENU):
            selected = i == self.menu_index
            a = theme.attr(theme.PAIR_HILITE if selected else theme.PAIR_NORMAL,
                           bold=selected)
            marker = "▶ " if selected else "  "
            try:
                win.addstr(top + i, left, f"{marker}{label}".ljust(width)[:width], a)
            except curses.error:
                pass

    def status_text(self) -> str:
        if self.message:
            return self.message
        buf = self.buffer
        mark = f" [{labels.EDITOR_MODIFIED}]" if buf.dirty else ""
        return (f"{self.path.name}{mark}   "
                f"Ln {buf.row + 1}, Col {buf.col + 1}   {labels.EDITOR_HINT}")

    # ── input ─────────────────────────────────────────────────────────────────
    def handle_key(self, key: int):
        self.message = ""
        if self.rename_mode:
            return self._handle_rename_key(key)
        if self.menu_open:
            return self._handle_menu_key(key)
        if key == 27:                              # Esc → menu
            self.menu_open = True
            self.menu_index = 0
            return None
        buf = self.buffer
        if key == curses.KEY_UP:
            buf.move_up()
        elif key == curses.KEY_DOWN:
            buf.move_down()
        elif key == curses.KEY_LEFT:
            buf.move_left()
        elif key == curses.KEY_RIGHT:
            buf.move_right()
        elif key == curses.KEY_HOME:
            buf.move_home()
        elif key == curses.KEY_END:
            buf.move_end()
        elif key == curses.KEY_PPAGE:
            buf.move_page(-self._page)
        elif key == curses.KEY_NPAGE:
            buf.move_page(self._page)
        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            buf.newline()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            buf.backspace()
        elif key == curses.KEY_DC:
            buf.delete()
        elif key == ord("\t"):
            buf.insert(TAB_SPACES)
        elif 32 <= key <= 126:
            buf.insert(chr(key))
        return None

    def _handle_menu_key(self, key: int):
        if key == 27:                              # Esc again → back to editing
            self.menu_open = False
            return None
        if key in KEYS_UP:
            self.menu_index = (self.menu_index - 1) % len(self._MENU)
        elif key in KEYS_DOWN:
            self.menu_index = (self.menu_index + 1) % len(self._MENU)
        elif key in KEYS_SELECT:
            choice = self._MENU[self.menu_index]
            self.menu_open = False
            if choice == labels.EDITOR_MENU_SAVE:
                if self.save():
                    return "close"
            elif choice == labels.EDITOR_MENU_RENAME:
                self.rename_mode = True
                self.rename_edit = LineEdit(limit=48, value=self.path.stem)
            elif choice == labels.EDITOR_MENU_DISCARD:
                return "close"
            # RETURN: back to editing
        return None

    def _handle_rename_key(self, key: int):
        result = self.rename_edit.handle(key)
        if result == "cancel":
            self.rename_mode = False
            return None
        if result != "submit":
            return None
        self.rename_mode = False
        name = self.rename_edit.value.strip()
        if not name:
            return None
        new_path = self.path.with_name(f"{notesdb.slugify(name)}{self.path.suffix}")
        if new_path == self.path:
            return None
        if new_path.exists():
            self.message = labels.EDITOR_RENAME_EXISTS
            return None
        try:
            if self.path.exists():
                self.path.rename(new_path)
            self.path = new_path
        except OSError as exc:
            self.message = labels.EDITOR_SAVE_FAILED.format(err=exc)
            return None
        return "renamed"


class EditorScreen(Screen):
    """Pushable wrapper: `return EditorScreen(path)` from any menu action.

    `title_for`, if given, recomputes the header after a rename (the Esc
    menu's RENAME option) so the title reflects the file's new name — e.g.
    dated-entry screens pass a callback that keeps their fixed prefix and
    only swaps in the new stem. Defaults to the bare stem.
    """

    def __init__(self, path: Path, *, title: str = "", create_text: str = "",
                 wrap: bool = True, title_for=None):
        self.editor = Editor(path, create_text=create_text, wrap=wrap)
        self.title = title or labels.EDITOR_TITLE
        self.subtitle = labels.EDITOR_SUBTITLE
        self._title_for = title_for or (lambda p: p.stem)

    def draw(self, win, top: int, left: int) -> None:
        self.editor.draw(win, top, left)

    def status_text(self) -> str:
        return self.editor.status_text()

    def handle_key(self, key: int, app):
        result = self.editor.handle_key(key)
        if result == "close":
            return POP
        if result == "renamed":
            self.title = self._title_for(self.editor.path)
        return None
