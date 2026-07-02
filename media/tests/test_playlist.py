from pathlib import Path

from foundationmedia.library import Track
from foundationmedia.playlist import Playlist


def t(name: str) -> Track:
    return Track(path=Path(f"{name}.wav"), name=name, needs_engine=False)


def test_empty_playlist():
    pl = Playlist()
    assert len(pl) == 0
    assert pl.current is None
    assert pl.advance() is None
    assert pl.back() is None
    assert pl.jump(0) is None


def test_add_and_advance():
    pl = Playlist()
    pl.add(t("a"))
    pl.add(t("b"))
    assert pl.current is None            # nothing selected until advance/jump
    assert pl.advance().name == "a"
    assert pl.current.name == "a"
    assert pl.advance().name == "b"
    assert pl.advance() is None          # exhausted, no repeat
    assert pl.current.name == "b"        # cursor stays put


def test_repeat_wraps():
    pl = Playlist()
    pl.add(t("a"))
    pl.add(t("b"))
    pl.repeat = True
    pl.jump(1)
    assert pl.advance().name == "a"      # wrapped


def test_back_stays_on_first():
    pl = Playlist()
    pl.add(t("a"))
    pl.add(t("b"))
    pl.jump(1)
    assert pl.back().name == "a"
    assert pl.back().name == "a"         # no wrap backwards


def test_play_now_appends_and_selects():
    pl = Playlist()
    pl.add(t("a"))
    track = pl.play_now(t("b"))
    assert track.name == "b"
    assert pl.index == 1
    assert pl.current.name == "b"


def test_remove_before_current_shifts_cursor():
    pl = Playlist()
    for n in "abc":
        pl.add(t(n))
    pl.jump(2)
    pl.remove(0)
    assert pl.current.name == "c"
    assert pl.index == 1


def test_remove_current_keeps_position():
    pl = Playlist()
    for n in "abc":
        pl.add(t(n))
    pl.jump(1)
    pl.remove(1)
    assert pl.current.name == "c"        # next track slid into the slot


def test_remove_current_at_end_clamps():
    pl = Playlist()
    for n in "ab":
        pl.add(t(n))
    pl.jump(1)
    pl.remove(1)
    assert pl.current.name == "a"


def test_remove_last_track_empties():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)
    pl.remove(0)
    assert pl.current is None
    assert pl.index == -1


def test_remove_out_of_range_is_noop():
    pl = Playlist()
    pl.add(t("a"))
    pl.remove(5)
    pl.remove(-1)
    assert len(pl) == 1


def test_clear():
    pl = Playlist()
    pl.add(t("a"))
    pl.jump(0)
    pl.clear()
    assert len(pl) == 0
    assert pl.current is None
