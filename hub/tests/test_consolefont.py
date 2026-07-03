"""Headless tests for the console text-size setting (feedback #1).

setfont itself is a VT operation we can't run in CI, so these cover the pure
logic: the size table, config read/write round-trips, and the graceful-
degradation status strings. FOUNDATIONHUB_ETC is pointed at a tmp dir so no real
/etc is touched and setfont is never on PATH.
"""
import foundationhub.consolefont as consolefont


def _use_tmp_etc(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDATIONHUB_ETC", str(tmp_path))
    return tmp_path


# ── the size table ────────────────────────────────────────────────────────────

def test_default_is_the_2x_face():
    # Operator direction: default is twice the original 8×16 (ter-v16b) face.
    assert consolefont.DEFAULT_FONT == "ter-v32b"
    assert consolefont._by_font(consolefont.DEFAULT_FONT).note == "16×32"


def test_every_size_has_a_unique_face():
    fonts = [s.font for s in consolefont.SIZES]
    assert len(fonts) == len(set(fonts))
    assert "ter-v16b" in fonts and "ter-v32b" in fonts


# ── persistence round-trip ────────────────────────────────────────────────────

def test_get_font_defaults_when_unset(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    assert consolefont.get_font() == consolefont.DEFAULT_FONT


def test_save_then_get_round_trips(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    assert consolefont.save_font("ter-v24b") is True
    assert consolefont.get_font() == "ter-v24b"
    assert (tmp_path / "console-font").read_text().strip() == "ter-v24b"


def test_save_rejects_unknown_face(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    assert consolefont.save_font("comic-sans") is False
    # nothing written, so a read still yields the default
    assert consolefont.get_font() == consolefont.DEFAULT_FONT


def test_get_font_ignores_a_garbage_file(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    (tmp_path / "console-font").write_text("not-a-real-face\n")
    # a hand-edited/corrupt file must not wedge the console
    assert consolefont.get_font() == consolefont.DEFAULT_FONT


# ── labels ────────────────────────────────────────────────────────────────────

def test_current_label_reflects_saved_choice(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    consolefont.save_font("ter-v16b")
    assert consolefont.current_label() == "NORMAL"


def test_label_for_unknown_returns_the_raw_name():
    assert consolefont.label_for("ter-v99z") == "ter-v99z"


# ── set_font status strings (off-device: setfont absent) ──────────────────────

def test_set_font_off_device_persists_and_reports_next_login(tmp_path, monkeypatch):
    _use_tmp_etc(tmp_path, monkeypatch)
    monkeypatch.setattr(consolefont.shutil, "which", lambda _: None)
    msg = consolefont.set_font("ter-v24b")
    assert "LARGE" in msg and "next login" in msg
    assert consolefont.get_font() == "ter-v24b"


def test_set_font_rejects_unknown():
    assert consolefont.set_font("nope") == "unknown text size"
