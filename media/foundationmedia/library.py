"""The account's music library: a scan of its own media directory.

Per-user by construction — same `FOUNDATIONHUB_DATA` root and `users/<name>/`
layout the notes suite and the games use, so media counts toward the same
quota'd space rather than inventing a second one. Users never see each
other's libraries because the scan root *is* the active account's dir.

Plain functions over explicit paths so everything is testable without curses
or a real account (tests pass a tmp_path; the real program uses
`media_dir()`). NOT exempt from Frank: these are ordinary files under the
account's data dir, visible to Frank's watchers like anything else.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Formats the pure-stdlib decode path handles on its own (BUILD-QUEUE §4
# option (c): this set is the whole library on the Pocket8086 tier).
STDLIB_EXTS = frozenset({".wav", ".aiff", ".aif"})
# Formats that need the ffmpeg decode engine (broad-format path).
ENGINE_EXTS = frozenset({".mp3", ".flac", ".ogg", ".opus", ".m4a",
                         ".aac", ".wma", ".mka"})
MEDIA_SUBDIR = "media"


def data_root() -> Path:
    return Path(os.environ.get("FOUNDATIONHUB_DATA",
                os.path.expanduser("~/.local/share/foundationhub")))


def active_username() -> str:
    """Whoever is logged into the Hub right now. foundationmedia is spawned as
    a child of the Hub (`Launch`), which sets FOUNDATIONHUB_USER in its own
    environment before exec'ing — inherited here. Falls back to the file the
    Hub publishes for the same purpose, then "guest" off-device."""
    name = os.environ.get("FOUNDATIONHUB_USER")
    if name:
        return name
    active_file = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER",
                                      "/run/foundationhub/active-user"))
    try:
        name = active_file.read_text().strip()
    except OSError:
        name = ""
    return name or "guest"


def media_dir(root: Path | None = None, username: str | None = None) -> Path:
    root = root if root is not None else data_root()
    username = username if username is not None else active_username()
    return root / "users" / username / MEDIA_SUBDIR


@dataclass(frozen=True)
class Track:
    path: Path
    name: str          # display name: path relative to the media dir, no ext
    needs_engine: bool  # True -> unplayable without ffmpeg


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in STDLIB_EXTS or path.suffix.lower() in ENGINE_EXTS


def scan(root: Path) -> list[Track]:
    """All media files under `root`, recursively, sorted by display name.
    Missing root = empty library (first run; the TUI creates it)."""
    if not root.is_dir():
        return []
    tracks = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not is_media_file(path):
            continue
        rel = path.relative_to(root)
        name = str(rel.with_suffix("")).replace(os.sep, "/")
        tracks.append(Track(path=path, name=name,
                            needs_engine=path.suffix.lower() in ENGINE_EXTS))
    tracks.sort(key=lambda t: t.name.lower())
    return tracks
