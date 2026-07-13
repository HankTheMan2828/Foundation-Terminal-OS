"""System Status must show WHY Frank is down, not just 'non-functional'.

frank_health() returns '' when the daemon is reachable, and otherwise a one-line
summary pulled from frankd's health breadcrumb (status tag + the last traceback
line) — the only way to diagnose a dead overseer on a no-shell locked kiosk.
"""
from foundationhub import session


def test_empty_when_frank_alive(monkeypatch):
    monkeypatch.setattr(session.FrankClient, "is_alive", lambda self: True)
    assert session.frank_health() == ""


def test_reports_startup_error_line(tmp_path, monkeypatch):
    monkeypatch.setattr(session.FrankClient, "is_alive", lambda self: False)
    hp = tmp_path / "frankd.health"
    hp.write_text("status=startup-error\nts=123\n"
                  "Traceback (most recent call last):\n"
                  "  File \"x\", line 1, in <module>\n"
                  "ModuleNotFoundError: No module named 'frankd'\n")
    monkeypatch.setattr(session, "FRANK_HEALTH", hp)
    reason = session.frank_health()
    assert reason.startswith("startup-error:")
    assert "ModuleNotFoundError" in reason


def test_hint_when_no_health_file(tmp_path, monkeypatch):
    monkeypatch.setattr(session.FrankClient, "is_alive", lambda self: False)
    monkeypatch.setattr(session, "FRANK_HEALTH", tmp_path / "absent")
    assert "no health file" in session.frank_health()


def test_local_ai_health_empty_when_up(monkeypatch):
    monkeypatch.setattr(session, "check_local_ai", lambda: True)
    assert session.local_ai_health() == ""


def test_local_ai_health_reads_status_file(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "check_local_ai", lambda: False)
    p = tmp_path / "ai-status"
    p.write_text("state=idle\ndetail=missing: runtime\n")
    monkeypatch.setattr(session, "AI_STATUS_PATHS", (p,))
    reason = session.local_ai_health()
    assert "idle" in reason
    assert "runtime" in reason
