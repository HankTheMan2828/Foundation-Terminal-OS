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

from .. import labels, session
from ..app import MenuScreen, Launch
from ..ui import MenuItem

DATA = Path(os.environ.get("ZENHUB_DATA",
            os.path.expanduser("~/.local/share/zenhub")))
# The external editor/browser are TEMPORARY stand-ins: the decided design is a
# full in-house notes suite (editor + tag/search browser inside the Hub) — see
# docs/OPEN-QUESTIONS.md §10. One-editor policy: whatever edits here is what
# edits everywhere.
EDITOR = os.environ.get("EDITOR", "nvim")


def _user_dir() -> Path:
    """Each logical account gets its own notes space (docs/USERS.md). On the
    target this will live inside the account's quota'd home; in the layered
    scaffold it's namespaced under the shared data dir."""
    acct = session.get_active_account()
    if acct is not None:
        return DATA / "users" / acct.username
    return DATA


def _today_entry() -> list[str]:
    journal = _user_dir() / "journal"
    journal.mkdir(parents=True, exist_ok=True)
    path = journal / f"{_dt.date.today().isoformat()}.md"
    if not path.exists():
        path.write_text(f"# {_dt.date.today().isoformat()}\n\n")
    return [EDITOR, str(path)]


def screen():
    notes = _user_dir() / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    items = [
        MenuItem(labels.NOTE_JOURNAL, lambda a: Launch(_today_entry()),
                 hint="today, dated"),
        MenuItem(labels.NOTE_TAGGED, lambda a: Launch(["ranger", str(notes)]),
                 hint="tagged notes dir"),
    ]
    return MenuScreen(labels.NOTES, items,
                      subtitle="not exempt from the overseer (§5)")
