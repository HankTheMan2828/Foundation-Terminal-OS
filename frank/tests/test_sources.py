"""operator_home() must resolve the real home, not assume /home/<name>.

Another machine's layout (or a mini PC installed with a different home
scheme) must not break the shell-history collector — the path comes from the
passwd database, with an env override for tests/off-target runs.
"""
from pathlib import Path

import pytest

from frankd import sources


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
