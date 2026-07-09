"""Frank must self-report a startup crash to an operator-readable health file.

On a no-shell locked kiosk the journal can't be read, so a dead overseer was
undiagnosable. daemon.main() now captures a construction failure into the health
breadcrumb (status + traceback) before re-raising for systemd, and _write_health
is best-effort (never itself crashes Frank).
"""
import pytest

import frankd.daemon as daemon


def test_startup_error_is_captured_to_health(tmp_path, monkeypatch):
    hp = tmp_path / "frankd.health"
    monkeypatch.setattr(daemon, "_HEALTH_PATH", hp)

    class Boom(Exception):
        pass

    def boom(*a, **k):
        raise Boom("cannot construct frank")

    monkeypatch.setattr(daemon, "Frank", boom)
    with pytest.raises(Boom):
        daemon.main()

    text = hp.read_text()
    assert "status=startup-error" in text
    assert "cannot construct frank" in text   # the real error is preserved


def test_write_health_roundtrip(tmp_path, monkeypatch):
    hp = tmp_path / "sub" / "frankd.health"     # parent created on demand
    monkeypatch.setattr(daemon, "_HEALTH_PATH", hp)
    daemon._write_health("running")
    assert "status=running" in hp.read_text()
