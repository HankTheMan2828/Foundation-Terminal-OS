"""Player state machine with fake decoder/output — no ALSA, no audio files,
no real time: threads run flat out over tiny fake chunks."""
import time
from pathlib import Path

from foundationmedia import alsa, decoders, player as player_mod
from foundationmedia.library import Track
from foundationmedia.player import Player, PAUSED, PLAYING, STOPPED
from foundationmedia.playlist import Playlist


def t(name: str) -> Track:
    return Track(path=Path(f"{name}.wav"), name=name, needs_engine=False)


class FakeDecoder:
    def __init__(self, chunks: int = 4, rate: int = 1000, channels: int = 1):
        self.rate = rate
        self.channels = channels
        self.duration = None
        self._left = chunks
        self.seeks: list[float] = []
        self.closed = False

    def read(self, frames: int) -> bytes:
        if self._left <= 0:
            return b""
        self._left -= 1
        return b"\x64\x00" * frames          # each sample = 100

    def seek(self, seconds: float) -> None:
        self.seeks.append(seconds)

    def close(self) -> None:
        self.closed = True


class FakeOutput:
    instances: list["FakeOutput"] = []

    def __init__(self, rate: int, channels: int):
        self.rate = rate
        self.channels = channels
        self.writes: list[bytes] = []
        self.dropped = 0
        self.closed = False
        FakeOutput.instances.append(self)

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def drop(self) -> None:
        self.dropped += 1

    def close(self, *, drain: bool = False) -> None:
        self.closed = True


def make_player(playlist, decoder_factory=None):
    FakeOutput.instances = []
    made = []

    def default_factory(path):
        dec = FakeDecoder()
        made.append(dec)
        return dec

    p = Player(playlist,
               decoder_factory=decoder_factory or default_factory,
               output_factory=FakeOutput,
               chunk_frames=8)
    return p, made


def wait_stopped(p: Player, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if p.state == STOPPED and (p._thread is None or not p._thread.is_alive()):
            return
        time.sleep(0.01)
    raise AssertionError(f"player did not stop (state={p.state})")


def test_plays_queue_to_end_and_stops():
    pl = Playlist()
    pl.add(t("a"))
    pl.add(t("b"))
    pl.jump(0)
    p, made = make_player(pl)
    p.play_current()
    wait_stopped(p)
    assert len(made) == 2                    # auto-advanced to track b
    assert all(d.closed for d in made)
    assert all(o.closed for o in FakeOutput.instances)
    assert p.track is None
    assert pl.index == 1                     # cursor ended on the last track


def test_volume_scaling_applied():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)
    p, _ = make_player(pl)
    p.volume = 50
    p.play_current()
    wait_stopped(p)
    written = b"".join(b for o in FakeOutput.instances for b in o.writes)
    assert written == b"\x32\x00" * (len(written) // 2)   # 100 -> 50 everywhere


def test_decode_error_reports_and_stops():
    pl = Playlist()
    pl.add(t("bad"))
    pl.add(t("good"))
    pl.jump(0)

    def factory(path):
        raise decoders.DecodeError("broken header")

    p, _ = make_player(pl, decoder_factory=factory)
    p.play_current()
    wait_stopped(p)
    assert "broken header" in p.error
    assert pl.index == 0                     # did not machine-gun onward


def test_output_error_reports_and_stops():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)
    dec = FakeDecoder()

    class NoAudio:
        def __init__(self, rate, channels):
            raise alsa.OutputError("libasound not available")

    p = Player(pl, decoder_factory=lambda path: dec,
               output_factory=NoAudio, chunk_frames=8)
    p.play_current()
    wait_stopped(p)
    assert "libasound" in p.error
    assert dec.closed                        # decoder not leaked


def test_pause_resume_flags():
    pl = Playlist()
    p, _ = make_player(pl)
    p.toggle_pause()                         # no-op while stopped
    assert p.state == STOPPED
    p.state = PLAYING
    p.toggle_pause()
    assert p.state == PAUSED
    assert not p._resume.is_set()
    p.toggle_pause()
    assert p.state == PLAYING
    assert p._resume.is_set()


def test_seek_clamps():
    pl = Playlist()
    p, _ = make_player(pl)
    p.seek(-5)                               # stopped: ignored
    assert p._seek_to is None
    p.state = PLAYING
    p._position = 10.0
    p.seek(-20)
    assert p._seek_to == 0.0
    p.duration = 30.0
    p._position = 28.0
    p.seek(+10)
    assert p._seek_to == 29.5                # duration - 0.5 guard


def test_adjust_volume_clamps():
    pl = Playlist()
    p, _ = make_player(pl)
    p.volume = 98
    assert p.adjust_volume(+5) == 100
    p.volume = 3
    assert p.adjust_volume(-5) == 0


def test_next_at_end_stops_prev_restarts():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)
    p, made = make_player(pl)
    p.play_current()
    wait_stopped(p)
    p.next()                                 # exhausted queue -> stop, no crash
    assert p.state == STOPPED
    p.prev()                                 # back onto the first track
    wait_stopped(p)
    assert len(made) >= 2


def test_stop_supersedes_running_thread():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)

    def endless_factory(path):
        return FakeDecoder(chunks=10_000_000)

    p = Player(pl, decoder_factory=endless_factory,
               output_factory=FakeOutput, chunk_frames=8)
    FakeOutput.instances = []
    p.play_current()
    time.sleep(0.05)
    assert p.state == PLAYING
    p.stop()
    wait_stopped(p)
    assert p.track is None
