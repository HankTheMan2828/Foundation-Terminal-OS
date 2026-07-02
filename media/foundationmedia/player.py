"""The playback engine: one feed thread pumping decoder -> volume -> output.

The curses UI never touches audio directly; it calls the control methods
here (play/pause/stop/seek/volume/next/prev) and reads the status fields
(state, position, duration, error) to draw the now-playing line. The feed
thread owns the decoder and the ALSA device; a generation counter makes
every control change race-free: bumping it tells the current thread its
work is stale, so it exits at the next chunk boundary.

Decoder and output are injected factories, so the whole state machine is
unit-tested with fakes (tests/test_player.py) — no ALSA, no files, no
sleeping on real audio.
"""
from __future__ import annotations

import threading

from . import alsa, decoders, pcm
from .playlist import Playlist

STOPPED = "stopped"
PLAYING = "playing"
PAUSED = "paused"

# 2048 frames ≈ 46 ms at 44.1 kHz: small enough that pause/stop/seek feel
# instant, big enough that the Python loop overhead stays negligible.
CHUNK_FRAMES = 2048


class Player:
    def __init__(self, playlist: Playlist, *,
                 decoder_factory=decoders.open_decoder,
                 output_factory=alsa.AlsaOutput,
                 chunk_frames: int = CHUNK_FRAMES):
        self.playlist = playlist
        self._decoder_factory = decoder_factory
        self._output_factory = output_factory
        self._chunk_frames = chunk_frames

        self.state = STOPPED
        self.volume = 80             # 0..100, software-scaled (pcm.py)
        self.error = ""              # last failure, for the status bar
        self.track = None            # library.Track being played
        self.duration: float | None = None

        self._lock = threading.Lock()      # guards playlist + control fields
        self._resume = threading.Event()   # cleared = paused
        self._resume.set()
        self._generation = 0
        self._thread: threading.Thread | None = None
        self._seek_to: float | None = None
        self._position = 0.0

    # ── status (read by the UI every tick) ───────────────────────────────

    @property
    def position(self) -> float:
        return self._position

    # ── controls (called from the UI thread) ─────────────────────────────

    def play_current(self) -> None:
        """(Re)start whatever the playlist cursor points at."""
        with self._lock:
            track = self.playlist.current
        if track is not None:
            self._start(track)

    def toggle_pause(self) -> None:
        if self.state == PLAYING:
            self.state = PAUSED
            self._resume.clear()
        elif self.state == PAUSED:
            self.state = PLAYING
            self._resume.set()

    def stop(self) -> None:
        self._halt_thread()
        self.state = STOPPED
        self.track = None
        self._position = 0.0
        self.duration = None

    def next(self) -> None:
        with self._lock:
            track = self.playlist.advance()
        if track is not None:
            self._start(track)
        else:
            self.stop()

    def prev(self) -> None:
        with self._lock:
            track = self.playlist.back()
        if track is not None:
            self._start(track)

    def seek(self, delta: float) -> None:
        """Relative seek; the feed thread applies it at the next chunk."""
        if self.state not in (PLAYING, PAUSED):
            return
        target = max(0.0, self._position + delta)
        if self.duration is not None:
            target = min(target, max(0.0, self.duration - 0.5))
        self._seek_to = target

    def adjust_volume(self, delta: int) -> int:
        self.volume = max(0, min(100, self.volume + delta))
        return self.volume

    def close(self) -> None:
        self.stop()

    # ── the feed thread ──────────────────────────────────────────────────

    def _start(self, track) -> None:
        self._halt_thread()
        self.error = ""
        self.track = track
        self.duration = None
        self._position = 0.0
        self._seek_to = None
        self.state = PLAYING
        self._resume.set()
        gen = self._generation
        self._thread = threading.Thread(target=self._run, args=(gen, track),
                                        daemon=True)
        self._thread.start()

    def _halt_thread(self) -> None:
        self._generation += 1        # any running loop is now stale
        self._resume.set()           # unblock a paused loop so it can exit
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2)
        self._thread = None

    def _stale(self, gen: int) -> bool:
        return gen != self._generation

    def _run(self, gen: int, track) -> None:
        """Plays `track`, then auto-advances through the queue until it is
        exhausted, a control call supersedes this thread, or an error."""
        while track is not None and not self._stale(gen):
            ok = self._play_one(gen, track)
            if not ok or self._stale(gen):
                return
            with self._lock:
                if self._stale(gen):
                    return
                track = self.playlist.advance()
                if track is not None:
                    self.track = track
                    self.duration = None
                    self._position = 0.0
                    self._seek_to = None
        if not self._stale(gen):
            self.state = STOPPED
            self.track = None
            self._position = 0.0

    def _play_one(self, gen: int, track) -> bool:
        """One track, start to finish. Returns False on error (self.error
        is set and the loop stops rather than machine-gunning failures)."""
        try:
            dec = self._decoder_factory(track.path)
        except decoders.DecodeError as exc:
            self.error = f"{track.name}: {exc}"
            self.state = STOPPED
            return False
        try:
            out = self._output_factory(dec.rate, dec.channels)
        except alsa.OutputError as exc:
            dec.close()
            self.error = str(exc)
            self.state = STOPPED
            return False

        self.duration = dec.duration
        base = 0.0
        fed = 0     # bytes fed since `base`
        try:
            while not self._stale(gen):
                if not self._resume.is_set():          # paused
                    self._resume.wait(timeout=0.2)
                    continue
                target = self._seek_to
                if target is not None:
                    self._seek_to = None
                    dec.seek(target)
                    out.drop()
                    base, fed = target, 0
                data = dec.read(self._chunk_frames)
                if not data:
                    out.close(drain=True)
                    return True                        # natural end of track
                if self._stale(gen):
                    break
                out.write(pcm.scale_volume(data, self.volume))
                fed += len(data)
                self._position = base + pcm.bytes_to_seconds(
                    fed, dec.rate, dec.channels)
            out.close(drain=False)
            return True
        except alsa.OutputError as exc:
            self.error = str(exc)
            self.state = STOPPED
            try:
                out.close(drain=False)
            except alsa.OutputError:
                pass
            return False
        finally:
            dec.close()
