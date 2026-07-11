"""User-visible strings — every one lives here (matches the Hub's
labels.py convention: no literal UI strings scattered through the modules)."""
from __future__ import annotations

MEDIA_TITLE = "FOUNDATION MEDIA"
MEDIA_TAGLINE = "one player, from the Foundation"

VIEW_LIBRARY = "LIBRARY"
VIEW_QUEUE = "QUEUE"

HINT_LIBRARY = ("UP/DOWN select · ENTER play · A queue · TAB queue view · "
                "SPACE pause · +/- vol · ESC/Q quit")
HINT_QUEUE = ("UP/DOWN select · ENTER jump · X remove · C clear · TAB library · "
              "SPACE pause · ESC/Q quit")
HINT_SEEK = "LEFT/RIGHT seek 5s · N next · B previous · R repeat"

STATE_PLAYING = "PLAYING"
STATE_PAUSED = "PAUSED"
STATE_STOPPED = "STOPPED"

NOW_PLAYING = "NOW PLAYING"
VOLUME = "VOL"
REPEAT_ON = "REPEAT"

EMPTY_LIBRARY = "no media files — add audio to your media directory"
EMPTY_QUEUE = "queue is empty — press A in the library to add tracks"
NEEDS_ENGINE = "requires decode engine (ffmpeg) — not installed"

QUEUED = "queued"
NOT_A_TERMINAL = "terminal too small — resize and retry"
