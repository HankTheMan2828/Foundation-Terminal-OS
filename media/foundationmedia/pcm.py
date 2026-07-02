"""PCM helpers: software volume and time formatting. Pure stdlib, no audioop
(removed in Python 3.13) — scaling is an `array('h')` integer loop, cheap
enough for real-time audio (a 44.1 kHz stereo second is ~88k samples; the
loop costs a few percent of one core, acceptable even on the weak tiers).

Everything here is bytes-in/bytes-out and unit-tested (tests/test_pcm.py).
All PCM in this program is signed 16-bit little-endian interleaved (s16le):
the stdlib decoder converts to it, ffmpeg is asked for it explicitly, ALSA
is opened with it. One wire format keeps every seam simple.
"""
from __future__ import annotations

import sys
from array import array

S16_BYTES = 2
_NATIVE_IS_LE = sys.byteorder == "little"


def scale_volume(data: bytes, volume: int) -> bytes:
    """Scale s16le PCM by an integer volume 0..100. 100 = passthrough."""
    if volume >= 100:
        return data
    if volume <= 0:
        return b"\x00" * len(data)
    samples = array("h")
    samples.frombytes(data)
    if not _NATIVE_IS_LE:
        samples.byteswap()
    for i in range(len(samples)):
        samples[i] = samples[i] * volume // 100
    if not _NATIVE_IS_LE:
        samples.byteswap()
    return samples.tobytes()


def u8_to_s16le(data: bytes) -> bytes:
    """Convert unsigned 8-bit PCM (old WAV files) to s16le."""
    out = array("h", bytearray(len(data) * S16_BYTES))
    for i, b in enumerate(data):
        out[i] = (b - 128) << 8
    if not _NATIVE_IS_LE:
        out.byteswap()
    return out.tobytes()


def swap16(data: bytes) -> bytes:
    """Byte-swap 16-bit samples (AIFF is big-endian PCM)."""
    samples = array("h")
    samples.frombytes(data)
    samples.byteswap()
    return samples.tobytes()


def bytes_to_seconds(nbytes: int, rate: int, channels: int) -> float:
    frame = S16_BYTES * max(1, channels)
    return nbytes / frame / max(1, rate)


def fmt_time(seconds: float) -> str:
    """mm:ss (or h:mm:ss past the hour) for the now-playing line."""
    s = max(0, int(seconds))
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def progress_bar(position: float, duration: float, width: int) -> str:
    """A fixed-width [####----] bar; duration 0/unknown = empty bar."""
    width = max(0, width)
    if width == 0:
        return ""
    if duration <= 0:
        return "-" * width
    filled = int(round(width * min(1.0, max(0.0, position / duration))))
    return "#" * filled + "-" * (width - filled)
