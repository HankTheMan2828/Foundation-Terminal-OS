"""operator_home() must resolve the real home, not assume /home/<name>.

Another machine's layout (or a mini PC installed with a different home
scheme) must not break the shell-history collector — the path comes from the
passwd database, with an env override for tests/off-target runs.

Also covers the `activity` collector — the Hub's per-action feed, which is the
main content source on this OS (no shell to leave a .bash_history).
"""
import json
from pathlib import Path

import pytest

from frankd import sources
from frankd.model import Source


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("FRANK_OPERATOR_HOME", raising=False)


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("FRANK_OPERATOR_HOME", "/srv/kiosk-home")
    assert sources.operator_home() == Path("/srv/kiosk-home")


def test_passwd_lookup_used_when_available(monkeypatch):
    class Entry:
        pw_dir = "/var/home/operator"

    class FakePwd:
        @staticmethod
        def getpwnam(name):
            assert name == sources.OPERATOR
            return Entry()

    monkeypatch.setattr(sources, "pwd", FakePwd())
    assert sources.operator_home() == Path("/var/home/operator")


def test_falls_back_to_conventional_layout(monkeypatch):
    class FakePwd:
        @staticmethod
        def getpwnam(name):
            raise KeyError(name)

    monkeypatch.setattr(sources, "pwd", FakePwd())
    assert sources.operator_home() == Path("/home") / sources.OPERATOR


def test_shell_history_reads_resolved_home(monkeypatch, tmp_path):
    (tmp_path / ".bash_history").write_text("nmap -sS target\n")
    monkeypatch.setenv("FRANK_OPERATOR_HOME", str(tmp_path))
    events = list(sources.shell_history({}))
    assert [e.text for e in events] == ["nmap -sS target"]


# ── activity collector (the Hub's per-action feed) ──────────────────────────

def _write_activity(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_activity_yields_new_lines_and_advances_cursor(monkeypatch, tmp_path):
    spool = tmp_path / "activity.log"
    monkeypatch.setattr(sources, "ACTIVITY_SPOOL", spool)
    _write_activity(spool, [
        {"ts": 100.0, "user": "alice", "kind": "launch", "text": "launch foundation-arcade"},
        {"ts": 101.0, "user": "alice", "kind": "note-save", "text": "note-save diary.md\nhello"},
    ])
    state: dict = {}
    events = list(sources.activity(state))
    assert [e.source for e in events] == [Source.ACTIVITY, Source.ACTIVITY]
    assert events[0].text == "launch foundation-arcade"
    assert events[0].user == "alice"
    assert events[0].ts == 100.0
    # Cursor advanced: a second poll with no new lines yields nothing.
    assert list(sources.activity(state)) == []
    # A newly appended line is picked up on the next poll.
    with spool.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": 102.0, "user": "alice", "kind": "chat",
                             "text": "chat how do I..."}) + "\n")
    more = list(sources.activity(state))
    assert [e.text for e in more] == ["chat how do I..."]


def test_activity_skips_blank_and_malformed_lines(monkeypatch, tmp_path):
    spool = tmp_path / "activity.log"
    monkeypatch.setattr(sources, "ACTIVITY_SPOOL", spool)
    spool.write_text(
        "\n"
        "not json at all\n"
        + json.dumps({"ts": 1.0, "user": "", "kind": "screen", "text": "screen NOTES"}) + "\n"
        + json.dumps({"ts": 2.0, "text": ""}) + "\n"   # empty text is dropped
    )
    events = list(sources.activity({}))
    assert [e.text for e in events] == ["screen NOTES"]


def test_activity_missing_spool_is_silent(monkeypatch, tmp_path):
    monkeypatch.setattr(sources, "ACTIVITY_SPOOL", tmp_path / "nope.log")
    assert list(sources.activity({})) == []


def test_activity_is_in_the_collector_set():
    assert sources.activity in sources.ALL
