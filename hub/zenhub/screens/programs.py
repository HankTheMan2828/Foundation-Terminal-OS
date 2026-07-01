"""Programs — general tools, each a Launch into a real console program (spec §5).

The Hub does not reimplement these; it shells out to ranger/btop/etc. and
resumes when they exit. Missing programs degrade to a status hint.
"""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen, Launch
from ..ui import MenuItem


def screen():
    items = [
        MenuItem(labels.PROG_FILES, lambda a: Launch(["ranger"]), hint="ranger"),
        MenuItem(labels.PROG_MEDIA, lambda a: Launch(["cmus"]), hint="cmus / mpv"),
        MenuItem(labels.PROG_MONITOR, lambda a: Launch(["btop"]), hint="btop"),
        MenuItem(labels.PROG_EDITOR, lambda a: Launch(["nvim"]), hint="editor"),
    ]
    return MenuScreen(labels.PROGRAMS, items)
