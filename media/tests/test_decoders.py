import wave
from array import array
from pathlib import Path

import pytest

from foundationmedia import decoders, pcm


def write_wav(path: Path, *, rate=8000, channels=1, width=2, seconds=1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        n = rate * seconds
        if width == 2:
            samples = array("h", [i % 1000 for i in range(n * channels)])
            w.writeframes(samples.tobytes())
        else:
            w.writeframes(bytes([i % 256 for i in range(n * channels)]))


def test_wav_decoder_basic(tmp_path):
    path = tmp_path / "tone.wav"
    write_wav(path, rate=8000, channels=2, seconds=2)
    dec = decoders.WavDecoder(path)
    assert dec.rate == 8000
    assert dec.channels == 2
    assert dec.duration == pytest.approx(2.0)
    data = dec.read(100)
    assert len(data) == 100 * 2 * pcm.S16_BYTES
    dec.close()


def test_wav_decoder_reads_to_eof(tmp_path):
    path = tmp_path / "short.wav"
    write_wav(path, rate=1000, seconds=1)
    dec = decoders.WavDecoder(path)
    total = 0
    while True:
        data = dec.read(256)
        if not data:
            break
        total += len(data)
    assert total == 1000 * pcm.S16_BYTES
    dec.close()


def test_wav_decoder_seek(tmp_path):
    path = tmp_path / "seek.wav"
    write_wav(path, rate=1000, seconds=2)
    dec = decoders.WavDecoder(path)
    dec.seek(1.0)
    remaining = 0
    while True:
        data = dec.read(256)
        if not data:
            break
        remaining += len(data)
    assert remaining == 1000 * pcm.S16_BYTES   # exactly the second half
    # seek past the end clamps -> immediate EOF, not an exception
    dec.seek(99.0)
    assert dec.read(16) == b""
    dec.close()


def test_wav_8bit_converted(tmp_path):
    path = tmp_path / "old.wav"
    write_wav(path, rate=1000, width=1, seconds=1)
    dec = decoders.WavDecoder(path)
    data = dec.read(4)
    assert len(data) == 4 * pcm.S16_BYTES      # widened to s16
    dec.close()


def test_wav_garbage_raises(tmp_path):
    path = tmp_path / "junk.wav"
    path.write_bytes(b"not a wav at all")
    with pytest.raises(decoders.DecodeError):
        decoders.WavDecoder(path)


def test_open_decoder_picks_stdlib_for_wav(tmp_path):
    path = tmp_path / "pick.wav"
    write_wav(path)
    dec = decoders.open_decoder(path)
    assert isinstance(dec, decoders.WavDecoder)
    dec.close()


def test_open_decoder_engine_format_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(decoders, "engine_available", lambda: False)
    with pytest.raises(decoders.DecodeError):
        decoders.open_decoder(tmp_path / "song.mp3")
