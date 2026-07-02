"""Decode engines (BUILD-QUEUE §4, option (c) — operator-approved hybrid):

* `WavDecoder` / `AiffDecoder` — pure stdlib. Fully in-house, zero external
  programs; this path alone is the Pocket8086-tier fallback.
* `FfmpegDecoder` — shells out to ffmpeg as a decode *engine* under the
  in-house UI (broad formats: mp3/flac/ogg/…). ffmpeg is optional at
  runtime: when absent, those formats are listed but honestly disabled.

Every decoder emits the one wire format (s16le interleaved, see pcm.py) so
the player and the ALSA output never care where the bytes came from.

Notes on the stdlib path: `wave` is safe long-term; `aifc` was removed from
the stdlib in Python 3.13, so AIFF import-guards it and falls back to the
ffmpeg engine (or an honest error) on newer interpreters.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import pcm

# The ffmpeg engine decodes everything to one canonical output format so the
# ALSA device only ever needs opening one way for engine-decoded tracks.
ENGINE_RATE = 44100
ENGINE_CHANNELS = 2


class DecodeError(Exception):
    """This file cannot be decoded on this machine (bad file, exotic
    subformat on the stdlib path, or engine formats without ffmpeg)."""


def engine_available() -> bool:
    return shutil.which("ffmpeg") is not None


class WavDecoder:
    """Stdlib `wave` PCM reader. 8-bit unsigned and 16-bit WAV; anything more
    exotic (24/32-bit, compressed) is routed to the ffmpeg engine instead."""

    def __init__(self, path: Path):
        import wave
        try:
            self._wav = wave.open(str(path), "rb")
        except (OSError, EOFError, wave.Error) as exc:
            raise DecodeError(str(exc)) from exc
        self._width = self._wav.getsampwidth()
        if self._width not in (1, 2):
            self._wav.close()
            raise DecodeError(f"{self._width * 8}-bit WAV needs the decode engine")
        self.rate = self._wav.getframerate()
        self.channels = self._wav.getnchannels()
        self.duration: float | None = self._wav.getnframes() / max(1, self.rate)

    def read(self, frames: int) -> bytes:
        data = self._wav.readframes(frames)
        if self._width == 1:
            return pcm.u8_to_s16le(data)
        return data

    def seek(self, seconds: float) -> None:
        frame = min(self._wav.getnframes(), max(0, int(seconds * self.rate)))
        self._wav.setpos(frame)

    def close(self) -> None:
        self._wav.close()


class AiffDecoder:
    """Stdlib `aifc` reader (16-bit; AIFF PCM is big-endian, so samples get
    byte-swapped into the s16le wire format). Unavailable on Python >= 3.13
    where aifc was removed — open_decoder() falls back to the engine there."""

    def __init__(self, path: Path):
        try:
            import aifc
        except ImportError as exc:
            raise DecodeError("aifc module unavailable (Python >= 3.13)") from exc
        try:
            self._aif = aifc.open(str(path), "rb")
        except (OSError, EOFError, aifc.Error) as exc:
            raise DecodeError(str(exc)) from exc
        if self._aif.getsampwidth() != 2:
            self._aif.close()
            raise DecodeError("only 16-bit AIFF on the stdlib path")
        self.rate = self._aif.getframerate()
        self.channels = self._aif.getnchannels()
        self.duration: float | None = self._aif.getnframes() / max(1, self.rate)

    def read(self, frames: int) -> bytes:
        return pcm.swap16(self._aif.readframes(frames))

    def seek(self, seconds: float) -> None:
        frame = min(self._aif.getnframes(), max(0, int(seconds * self.rate)))
        self._aif.setpos(frame)

    def close(self) -> None:
        self._aif.close()


class FfmpegDecoder:
    """ffmpeg as a decode engine: one child process per track, raw s16le on
    stdout. Seeking restarts the child with `-ss` (input-side = fast seek)."""

    def __init__(self, path: Path):
        if not engine_available():
            raise DecodeError("decode engine (ffmpeg) not installed")
        self._path = path
        self.rate = ENGINE_RATE
        self.channels = ENGINE_CHANNELS
        self.duration = probe_duration(path)
        self._proc: subprocess.Popen | None = None
        self._spawn(0.0)

    def _spawn(self, offset: float) -> None:
        self._kill()
        argv = ["ffmpeg", "-v", "quiet", "-nostdin"]
        if offset > 0:
            argv += ["-ss", f"{offset:.3f}"]
        argv += ["-i", str(self._path), "-f", "s16le", "-acodec", "pcm_s16le",
                 "-ac", str(self.channels), "-ar", str(self.rate), "-"]
        try:
            self._proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL,
                                          stdin=subprocess.DEVNULL)
        except OSError as exc:
            raise DecodeError(str(exc)) from exc

    def read(self, frames: int) -> bytes:
        if self._proc is None or self._proc.stdout is None:
            return b""
        want = frames * self.channels * pcm.S16_BYTES
        chunks = []
        while want > 0:
            data = self._proc.stdout.read(want)
            if not data:
                break
            chunks.append(data)
            want -= len(data)
        return b"".join(chunks)

    def seek(self, seconds: float) -> None:
        self._spawn(max(0.0, seconds))

    def close(self) -> None:
        self._kill()

    def _kill(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill()
            self._proc.wait(timeout=5)
        except Exception:
            pass
        if self._proc.stdout is not None:
            self._proc.stdout.close()
        self._proc = None


def probe_duration(path: Path) -> float | None:
    """Track length via ffprobe (ships with ffmpeg). None if unknowable —
    the UI shows an empty bar rather than lying."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=10)
        return float(res.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def open_decoder(path: Path):
    """Pick the engine for a file: stdlib first for its formats (fully
    in-house, and the only path on the Pocket8086 tier), ffmpeg for the rest
    or when the stdlib path can't handle a WAV/AIFF subformat."""
    ext = path.suffix.lower()
    if ext == ".wav":
        try:
            return WavDecoder(path)
        except DecodeError:
            if engine_available():
                return FfmpegDecoder(path)
            raise
    if ext in (".aiff", ".aif"):
        try:
            return AiffDecoder(path)
        except DecodeError:
            if engine_available():
                return FfmpegDecoder(path)
            raise
    return FfmpegDecoder(path)
