"""ALSA PCM output via ctypes — the fully in-house half of the hybrid
backend (BUILD-QUEUE §4 option (c)). Talks straight to libasound.so.2; no
aplay, no sound server assumed (the kiosk has no PipeWire/Pulse — plain
ALSA "default").

Off-target (this Windows dev box, or any machine without libasound) the
module degrades gracefully: `available()` is False and `AlsaOutput` raises
`OutputError`, which the player turns into an honest status line instead of
a crash — same pattern as the Hub's session.py helpers.

The call sequence is the simple one: snd_pcm_open + snd_pcm_set_params
(the one-call setup; no hw_params dance) + blocking snd_pcm_writei, with
-EPIPE (underrun after a pause) recovered via snd_pcm_prepare.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os

from . import pcm

SND_PCM_STREAM_PLAYBACK = 0
SND_PCM_FORMAT_S16_LE = 2
SND_PCM_ACCESS_RW_INTERLEAVED = 3
_EPIPE = 32
# ~200 ms of device buffer: deep enough that the feed thread isn't racing,
# shallow enough that pause/stop feel immediate.
_LATENCY_US = 200_000

_lib = None
_lib_tried = False


class OutputError(Exception):
    """No usable audio output on this machine."""


def _load():
    global _lib, _lib_tried
    if _lib_tried:
        return _lib
    _lib_tried = True
    names = ["libasound.so.2", "libasound.so"]
    found = ctypes.util.find_library("asound")
    if found:
        names.insert(0, found)
    for name in names:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        # snd_pcm_writei returns snd_pcm_sframes_t (a long): without an
        # explicit restype ctypes truncates it to int on LP64 — set the
        # signatures we rely on precisely.
        lib.snd_pcm_open.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        lib.snd_pcm_set_params.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_uint,
                                           ctypes.c_uint, ctypes.c_int,
                                           ctypes.c_uint]
        lib.snd_pcm_writei.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                       ctypes.c_ulong]
        lib.snd_pcm_writei.restype = ctypes.c_long
        lib.snd_pcm_prepare.argtypes = [ctypes.c_void_p]
        lib.snd_pcm_drain.argtypes = [ctypes.c_void_p]
        lib.snd_pcm_drop.argtypes = [ctypes.c_void_p]
        lib.snd_pcm_close.argtypes = [ctypes.c_void_p]
        lib.snd_strerror.argtypes = [ctypes.c_int]
        lib.snd_strerror.restype = ctypes.c_char_p
        _lib = lib
        return _lib
    return None


def available() -> bool:
    return _load() is not None


def _err(lib, code: int) -> str:
    try:
        return lib.snd_strerror(code).decode(errors="replace")
    except Exception:
        return f"ALSA error {code}"


class AlsaOutput:
    """One open PCM device, fixed rate/channels for the life of a track
    (each track opens its own — rates differ between files)."""

    def __init__(self, rate: int, channels: int):
        lib = _load()
        if lib is None:
            raise OutputError("libasound not available")
        self._lib = lib
        self._channels = channels
        self._frame_bytes = pcm.S16_BYTES * channels
        device = os.environ.get("FOUNDATIONMEDIA_ALSA_DEVICE", "default")
        self._pcm = ctypes.c_void_p()
        rc = lib.snd_pcm_open(ctypes.byref(self._pcm), device.encode(),
                              SND_PCM_STREAM_PLAYBACK, 0)
        if rc < 0:
            raise OutputError(_err(lib, rc))
        rc = lib.snd_pcm_set_params(self._pcm, SND_PCM_FORMAT_S16_LE,
                                    SND_PCM_ACCESS_RW_INTERLEAVED,
                                    channels, rate, 1, _LATENCY_US)
        if rc < 0:
            lib.snd_pcm_close(self._pcm)
            self._pcm = None
            raise OutputError(_err(lib, rc))

    def write(self, data: bytes) -> None:
        """Blocking interleaved write of s16le PCM. Underruns (resume after
        a pause let the buffer drain) are recovered, not fatal."""
        if self._pcm is None:
            return
        lib = self._lib
        offset = 0
        total_frames = len(data) // self._frame_bytes
        while offset < total_frames:
            chunk = data[offset * self._frame_bytes:]
            rc = lib.snd_pcm_writei(self._pcm, chunk, total_frames - offset)
            if rc == -_EPIPE:
                lib.snd_pcm_prepare(self._pcm)
                continue
            if rc < 0:
                raise OutputError(_err(lib, rc))
            offset += rc

    def drop(self) -> None:
        """Throw away anything buffered (stop/seek: silence *now*)."""
        if self._pcm is not None:
            self._lib.snd_pcm_drop(self._pcm)
            self._lib.snd_pcm_prepare(self._pcm)

    def close(self, *, drain: bool = False) -> None:
        if self._pcm is None:
            return
        if drain:
            self._lib.snd_pcm_drain(self._pcm)
        else:
            self._lib.snd_pcm_drop(self._pcm)
        self._lib.snd_pcm_close(self._pcm)
        self._pcm = None
