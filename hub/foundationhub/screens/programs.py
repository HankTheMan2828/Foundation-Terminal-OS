"""Programs — general tools (spec §5).

Direction is IN-HOUSE (docs/OPEN-QUESTIONS.md §10, hybrid model): the file
manager and system monitor become native Hub screens; media gets ONE separate
in-house player (`foundationmedia` — replaces the old cmus+mpv pair). The TEXT
EDITOR is the notes suite's in-house editor (queue §1) — nvim is retired;
one editor everywhere.

FILE MANAGER and SYSTEM MONITOR are now native too (queue §2/§3) — ranger and
btop are both retired. MEDIA now launches the in-house foundationmedia (§4) —
still a Launch by design (hybrid model: media is a separate program).
"""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen, Launch
from ..editor import EditorScreen
from ..ui import MenuItem
from .files import FileManagerScreen
from .monitor import MonitorScreen
from .notes import user_dir


def screen():
    items = [
        MenuItem(labels.PROG_FILES, lambda a: FileManagerScreen(),
                 hint="in-house"),
        # The ONE in-house player, as its own program (hybrid model). Audio
        # v1; video out of scope (BUILD-QUEUE §4).
        MenuItem(labels.PROG_MEDIA, lambda a: Launch(
                     ["foundationmedia"],
                     missing_hint="[ in-house player — not installed ]"),
                 hint="foundationmedia"),
        # Native Hub screen (in-house monitor) — btop retired, queue §3.
        MenuItem(labels.PROG_MONITOR, lambda a: MonitorScreen(),
                 hint="in-house"),
        # One-editor policy: THE editor, on the account's own scratch pad.
        MenuItem(labels.PROG_EDITOR,
                 lambda a: EditorScreen(user_dir() / "scratch.md"),
                 hint="in-house"),
    ]
    return MenuScreen(labels.PROGRAMS, items)
