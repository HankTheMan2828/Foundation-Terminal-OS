from pathlib import Path

from foundationmedia import library


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_scan_missing_root_is_empty(tmp_path):
    assert library.scan(tmp_path / "nope") == []


def test_scan_filters_and_sorts(tmp_path):
    _touch(tmp_path / "b.wav")
    _touch(tmp_path / "A.mp3")
    _touch(tmp_path / "notes.txt")           # not media
    _touch(tmp_path / "album" / "one.flac")
    tracks = library.scan(tmp_path)
    assert [t.name for t in tracks] == ["A", "album/one", "b"]  # case-insensitive sort
    assert all("notes" not in t.name for t in tracks)


def test_needs_engine_flag(tmp_path):
    _touch(tmp_path / "song.wav")
    _touch(tmp_path / "song.mp3")
    _touch(tmp_path / "song.aiff")
    by_ext = {t.path.suffix: t for t in library.scan(tmp_path)}
    assert not by_ext[".wav"].needs_engine
    assert not by_ext[".aiff"].needs_engine
    assert by_ext[".mp3"].needs_engine


def test_playable_without_engine(tmp_path):
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "b.ogg")
    tracks = library.scan(tmp_path)
    assert [t.name for t in library.playable(tracks, engine_available=False)] == ["a"]
    assert len(library.playable(tracks, engine_available=True)) == 2


def test_media_dir_is_per_user(tmp_path):
    d = library.media_dir(tmp_path, "henry")
    assert d == tmp_path / "users" / "henry" / "media"


def test_media_dir_uses_env_user(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDATIONHUB_USER", "vault-101")
    assert library.media_dir(tmp_path).name == "media"
    assert library.media_dir(tmp_path).parent.name == "vault-101"


def test_active_username_guest_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("FOUNDATIONHUB_USER", raising=False)
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVE_USER", str(tmp_path / "absent"))
    assert library.active_username() == "guest"
