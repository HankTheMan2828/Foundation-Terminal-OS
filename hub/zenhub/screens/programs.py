"""Programs — general tools (spec §5).

Direction is IN-HOUSE (docs/OPEN-QUESTIONS.md §10, hybrid model): the file
manager and system monitor become native Hub screens; media gets ONE separate
in-house player (`zenmedia` — replaces the old cmus+mpv pair); the editor
policy is one editor everywhere, delivered by the notes suite.

Until each in-house piece lands, the open-source stand-ins below remain so the
terminal stays usable day to day — every one of them is marked for
replacement, not endorsement.
"""
from __future__ import annotations

from .. import labels
from ..app import MenuScreen, Launch
from ..ui import MenuItem


def screen():
    items = [
        # TEMPORARY stand-in -> native Hub screen (in-house file manager).
        MenuItem(labels.PROG_FILES, lambda a: Launch(["ranger"]),
                 hint="temporary (ranger)"),
        # One in-house player, audio+video, as its own program (hybrid model).
        MenuItem(labels.PROG_MEDIA, lambda a: Launch(
                     ["zenmedia"],
                     missing_hint="[ in-house player — not built yet ]"),
                 hint="zenmedia"),
        # TEMPORARY stand-in -> native Hub screen (in-house monitor).
        MenuItem(labels.PROG_MONITOR, lambda a: Launch(["btop"]),
                 hint="temporary (btop)"),
        # One-editor policy: this becomes the notes suite's editor when it
        # lands; nvim is the interim fallback only.
        MenuItem(labels.PROG_EDITOR, lambda a: Launch(["nvim"]),
                 hint="temporary (nvim)"),
    ]
    return MenuScreen(labels.PROGRAMS, items)
