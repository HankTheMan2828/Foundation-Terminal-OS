from array import array

from foundationmedia import pcm


def s16(*values) -> bytes:
    a = array("h", values)
    if a.itemsize == 2 and pcm._NATIVE_IS_LE:
        return a.tobytes()
    a.byteswap()
    return a.tobytes()


def test_volume_full_is_passthrough():
    data = s16(100, -100, 32767)
    assert pcm.scale_volume(data, 100) is data


def test_volume_zero_is_silence():
    data = s16(100, -100)
    assert pcm.scale_volume(data, 0) == b"\x00" * len(data)


def test_volume_half():
    out = array("h")
    out.frombytes(pcm.scale_volume(s16(100, -100, 1), 50))
    if not pcm._NATIVE_IS_LE:
        out.byteswap()
    assert list(out) == [50, -50, 0]


def test_u8_to_s16le():
    out = array("h")
    out.frombytes(pcm.u8_to_s16le(bytes([128, 255, 0])))
    if not pcm._NATIVE_IS_LE:
        out.byteswap()
    assert list(out) == [0, 127 << 8, -128 << 8]


def test_swap16_roundtrip():
    data = s16(0x1234, -2)
    assert pcm.swap16(pcm.swap16(data)) == data


def test_bytes_to_seconds():
    # one second of 44.1kHz stereo s16le
    assert pcm.bytes_to_seconds(44100 * 2 * 2, 44100, 2) == 1.0
    assert pcm.bytes_to_seconds(0, 44100, 2) == 0.0


def test_fmt_time():
    assert pcm.fmt_time(0) == "0:00"
    assert pcm.fmt_time(65) == "1:05"
    assert pcm.fmt_time(3661) == "1:01:01"
    assert pcm.fmt_time(-5) == "0:00"


def test_progress_bar():
    assert pcm.progress_bar(5, 10, 10) == "#####-----"
    assert pcm.progress_bar(0, 10, 4) == "----"
    assert pcm.progress_bar(20, 10, 4) == "####"      # clamped
    assert pcm.progress_bar(5, 0, 4) == "----"        # unknown duration
    assert pcm.progress_bar(5, 10, 0) == ""
