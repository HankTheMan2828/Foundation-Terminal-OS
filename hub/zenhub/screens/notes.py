"""Personal File — the operator's own space (spec §5).

Two parts: a dated chronological journal and a separate tagged-notes area.
NOT exempt from Frank — the spec explicitly dropped an exempt/private zone
(§5, §9). These are ordinary files under the operator's data dir; Frank's
filesystem watcher sees them like anything else.
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .. import labels
from ..app import MenuScreen, Launch
from ..ui import MenuItem

DATA = Path(os.environ.get("ZENHUB_DATA",
            os.path.expanduser("~/.local/share/zenhub")))
JOURNAL = DATA / "journal"
NOTES = DATA / "notes"
EDITOR = os.environ.get("EDITOR", "nvim")


def _today_entry() -> list[str]:
    JOURNAL.mkdir(parents=True, exist_ok=True)
    path = JOURNAL / f"{_dt.date.today().isoformat()}.md"
    if not path.exists():
        path.write_text(f"# {_dt.date.today().isoformat()}\n\n")
    return [EDITOR, str(path)]


def screen():
    NOTES.mkdir(parents=True, exist_ok=True)
    items = [
        MenuItem(labels.NOTE_JOURNAL, lambda a: Launch(_today_entry()),
                 hint="today, dated"),
        MenuItem(labels.NOTE_TAGGED, lambda a: Launch(["ranger", str(NOTES)]),
                 hint="tagged notes dir"),
    ]
    return MenuScreen(labels.NOTES, items,
                      subtitle="not exempt from the overseer (§5)")
