"""The Hub's report-only activity feed (activity.py) and its editor hooks.

Everything the user does is supposed to reach Frank; these check that the Hub
actually writes the spool lines Frank's `activity` collector reads, that the
editor reports opens and content-bearing saves, and that a missing spool dir is
a silent no-op (off-device).
"""
import json

import pytest

from foundationhub import activity
from foundationhub.editor import Editor


def _read(spool):
    return [json.loads(line) for line in spool.read_text().splitlines() if line.strip()]


@pytest.fixture
def spool(tmp_path, monkeypatch):
    path = tmp_path / "activity.log"
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVITY_LOG", str(path))
    monkeypatch.setenv("FOUNDATIONHUB_USER", "tester")
    return path


def test_record_appends_a_json_line(spool):
    activity.record("launch", "foundation-chess --novice")
    rows = _read(spool)
    assert len(rows) == 1
    assert rows[0]["kind"] == "launch"
    assert rows[0]["text"] == "launch foundation-chess --novice"
    assert rows[0]["user"] == "tester"
    assert isinstance(rows[0]["ts"], (int, float))


def test_record_appends_not_overwrites(spool):
    activity.record("screen", "NOTES")
    activity.record("screen", "SETTINGS")
    assert [r["text"] for r in _read(spool)] == ["screen NOTES", "screen SETTINGS"]


def test_record_truncates_huge_payloads(spool):
    activity.record("note-save", "x" * 10000)
    assert len(_read(spool)[0]["text"]) < 5000
    assert _read(spool)[0]["text"].endswith("[truncated]")


def test_missing_spool_dir_is_silent(tmp_path, monkeypatch):
    # Point at a path under a file (so mkdir of the parent fails) — record must
    # swallow it rather than crash the Hub.
    (tmp_path / "afile").write_text("x")
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVITY_LOG", str(tmp_path / "afile" / "activity.log"))
    activity.record("screen", "NOTES")  # must not raise


def test_editor_open_and_save_are_reported(spool, tmp_path):
    note = tmp_path / "diary.md"
    ed = Editor(note, create_text="secret plans")
    # Opening the note is reported immediately.
    assert _read(spool)[-1]["text"] == "note-open diary.md"
    ed.buffer.insert("!")
    assert ed.save() is True
    save = _read(spool)[-1]
    assert save["kind"] == "note-save"
    # The content rides along so Frank's content-review tiers can see it.
    assert save["text"].startswith("note-save diary.md")
    assert "secret plans" in save["text"]
