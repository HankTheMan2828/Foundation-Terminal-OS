"""Report-only activity feed: the Hub tells Frank what the user does.

Everything the user does happens *inside the Hub* — there is no shell to leave
a `.bash_history` behind (docs/ARCHITECTURE.md: "the TUI is the login shell").
So the Hub is the source of truth for "the user's actions", and this module is
how Frank finally gets to see them: one JSON line per action, appended to an
append-only spool that Frank's `activity` collector (frank/frankd/sources.py)
reads on its poll interval.

**This is OBSERVATION, not control.** Appending a line grants the Hub no power
over Frank. The read-only Hub↔Frank IPC socket (session.py / frank/frankd/ipc.py)
is untouched; there is still no way to tune, disable, or influence Frank from the
operator session (spec §6, docs/ARCHITECTURE.md "Frank isolation"). The operator
can of course write noise into their *own* activity log — exactly as they could
edit their own `.bash_history` — but that grants no authority over Frank's
config, verdicts, or enforcement, all of which stay frank-only.

Best-effort by design: if the spool directory is absent (off-device dev, or
Frank not installed) every call is a silent no-op, so instrumentation can be
sprinkled through the Hub without any screen having to care whether Frank is
there.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Shared default path with Frank's collector; FOUNDATIONHUB_ACTIVITY_LOG lets
# tests/off-target runs redirect it. Resolved at call time so tests can point it
# somewhere writable without re-importing.
_DEFAULT = "/run/foundationhub/activity.log"

# Keep a single note/file body from ballooning one JSON line; content review
# only needs enough text to classify, not a whole novel.
_MAX_TEXT = 4000


def _spool() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_ACTIVITY_LOG", _DEFAULT))


def _current_user() -> str:
    """The active logical account, so records follow the person (docs/USERS.md)."""
    try:
        from . import session
        acct = session.get_active_account()
        if acct is not None:
            return acct.username
    except Exception:
        pass
    return os.environ.get("FOUNDATIONHUB_USER", "")


def record(kind: str, detail: str = "") -> None:
    """Append one action to the activity spool. Never raises.

    `kind` is a short verb tag (e.g. "launch", "screen", "note-open",
    "note-save", "chat"); `detail` is the human-readable payload (argv, file
    name, note body, chat text). Both flow to Frank as one ACTIVITY event whose
    text the rule engine can match and the sift/Overseer tiers can review.
    """
    detail = detail.strip()
    if len(detail) > _MAX_TEXT:
        detail = detail[:_MAX_TEXT] + " …[truncated]"
    text = f"{kind} {detail}".strip()
    entry = {"ts": time.time(), "user": _current_user(), "kind": kind, "text": text}
    path = _spool()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # off-device / not installed: the feed is best-effort, never fatal
