"""The playback queue: an ordered list of tracks and a cursor.

Pure data structure, no curses, no audio — the player asks it what to play
next; the TUI renders it. Unit-tested headlessly (tests/test_playlist.py).
"""
from __future__ import annotations

from .library import Track


class Playlist:
    def __init__(self):
        self.tracks: list[Track] = []
        self.index: int = -1        # -1 = nothing selected/playing yet
        self.repeat: bool = False   # loop the whole queue when it runs out

    def __len__(self) -> int:
        return len(self.tracks)

    @property
    def current(self) -> Track | None:
        if 0 <= self.index < len(self.tracks):
            return self.tracks[self.index]
        return None

    def add(self, track: Track) -> None:
        self.tracks.append(track)

    def remove(self, pos: int) -> None:
        if not (0 <= pos < len(self.tracks)):
            return
        del self.tracks[pos]
        if pos < self.index:
            self.index -= 1
        elif pos == self.index:
            # Current entry vanished; keep the cursor where the next track
            # now sits (or clamp off the end -> nothing current).
            if self.index >= len(self.tracks):
                self.index = -1 if not self.tracks else len(self.tracks) - 1

    def clear(self) -> None:
        self.tracks.clear()
        self.index = -1

    def jump(self, pos: int) -> Track | None:
        """Select an explicit queue position (ENTER in the queue view)."""
        if 0 <= pos < len(self.tracks):
            self.index = pos
            return self.tracks[pos]
        return None

    def advance(self) -> Track | None:
        """Next track, honouring repeat. None = queue exhausted (stop)."""
        if not self.tracks:
            self.index = -1
            return None
        nxt = self.index + 1
        if nxt >= len(self.tracks):
            if not self.repeat:
                return None
            nxt = 0
        self.index = nxt
        return self.tracks[nxt]

    def back(self) -> Track | None:
        """Previous track; stays on the first rather than wrapping."""
        if not self.tracks:
            return None
        self.index = max(0, self.index - 1)
        return self.tracks[self.index]

    def play_now(self, track: Track) -> Track:
        """ENTER in the library: append and jump straight to it."""
        self.tracks.append(track)
        self.index = len(self.tracks) - 1
        return track
