"""Regression: the Hub MUST poll frankd and surface what it returns.

Warnings and lockouts take the full screen (with a 2s hold); care lines still
ride the status bar calmly. These tests pin the consumer side without a real
curses loop: _poll_frank() routes each type correctly.
"""
import time
from pathlib import Path

from foundationhub import session
from foundationhub.app import App


class _FakeFrank:
    def __init__(self, resp):
        self.resp = resp
        self.calls = 0
        self.negotiate_calls = []

    def poll(self):
        self.calls += 1
        return self.resp

    def negotiate(self, plea):
        self.negotiate_calls.append(plea)
        return {"outcome": "denied", "removed": 0, "remaining": 90, "msg": "no"}


def _app(resp):
    # stdscr/root are only touched by run(), not by __init__/_poll_frank.
    app = App(object(), lambda app: object())
    app.frank = _FakeFrank(resp)
    app._last_frank_poll = -1e9   # bypass the throttle
    return app


def _acct(name="alice"):
    class _Acct:
        username = name
    return _Acct()


def test_poll_surfaces_care_line_calmly(monkeypatch):
    monkeypatch.setattr(session, "get_active_account", lambda: _acct())
    app = _app({"type": "care",
                "raw": "care msg=You matter. Please reach out to someone close.",
                "msg": "You matter. Please reach out to someone close."})
    app._poll_frank()
    assert "reach out to someone" in app.status_message.lower()
    assert app._status_warn is False          # supportive, not an alarm


def test_poll_warn_uses_full_screen_banner(monkeypatch):
    """Infractions must NOT be a one-liner — full screen, 2s hold."""
    seen = {}

    def fake_banner(self, lines, min_seconds=0, accept_keys=None):
        seen["lines"] = lines
        seen["min_seconds"] = min_seconds
        return ord(" ")

    monkeypatch.setattr(session, "get_active_account", lambda: _acct())
    app = _app({"type": "warn",
                "user": "alice",
                "delivery": "statusbar",
                "msg": "Minor infraction.",
                "matched": ""})
    monkeypatch.setattr(App, "_blocking_banner", fake_banner)
    app._poll_frank()
    assert any("INFRACTION" in ln or "infraction" in ln.lower()
               for ln in seen["lines"])
    assert seen["min_seconds"] >= 2.0
    # Status bar must NOT be the delivery path for warns anymore.
    assert app.status_message == ""


def test_poll_lockout_redacts_file_and_logs_out(monkeypatch, tmp_path):
    path = tmp_path / "note.md"
    path.write_text("before msfconsole after\n", encoding="utf-8")
    session.note_content_path(path)

    logged_out = {"done": False}

    def fake_logout(self, notice=""):
        logged_out["done"] = True
        logged_out["notice"] = notice

    def fake_banner(self, lines, min_seconds=0, accept_keys=None):
        # Accept immediately (simulate post-hold Enter).
        seen_lines.append(lines)
        return ord("\n")

    seen_lines = []
    app = _app({"type": "lockout",
                "scope": "session",
                "user": "alice",
                "remaining": "120",
                "negotiable": "1",
                "matched": "msfconsole",
                "msg": "Access suspended."})
    # Pretend someone is logged in so the lockout path runs.
    class _Acct:
        username = "alice"
    monkeypatch.setattr(session, "get_active_account", lambda: _Acct())
    monkeypatch.setattr(App, "_blocking_banner", fake_banner)
    monkeypatch.setattr(App, "logout_to_login", fake_logout)
    app._poll_frank()

    body = path.read_text(encoding="utf-8")
    assert "***" in body
    assert "msfconsole" not in body
    assert logged_out["done"] is True
    # Negotiation availability must be visible on the banner.
    flat = "\n".join(seen_lines[0])
    assert "AVAILABLE" in flat
    assert "Press N" in flat or "press N" in flat.lower()


def test_poll_lockout_states_when_not_negotiable(monkeypatch):
    seen = []

    def fake_banner(self, lines, min_seconds=0, accept_keys=None):
        seen.append(lines)
        return ord("\n")

    app = _app({"type": "lockout",
                "scope": "machine",
                "remaining": "60",
                "negotiable": "0",
                "matched": "",
                "msg": "Machine restricted."})
    class _Acct:
        username = "alice"
    monkeypatch.setattr(session, "get_active_account", lambda: _Acct())
    monkeypatch.setattr(App, "_blocking_banner",
                        lambda self, lines, min_seconds=0, accept_keys=None:
                        seen.append(lines) or ord("\n"))
    monkeypatch.setattr(App, "logout_to_login", lambda self, notice="": None)
    app._poll_frank()
    flat = "\n".join(seen[0])
    assert "NOT AVAILABLE" in flat


def test_poll_none_leaves_status_untouched():
    app = _app({"type": "NONE", "raw": "NONE"})
    app.status_message = ""
    app._poll_frank()
    assert app.status_message == ""


def test_poll_ignores_other_users_session_warn(monkeypatch):
    """Bob must not see Alice's session warn (multi-user isolation)."""
    seen = {}

    def fake_banner(self, lines, min_seconds=0, accept_keys=None):
        seen["lines"] = lines
        return ord(" ")

    class _Acct:
        username = "bob"

    app = _app({"type": "warn",
                "user": "alice",
                "delivery": "statusbar",
                "msg": "Minor infraction.",
                "matched": ""})
    monkeypatch.setattr(session, "get_active_account", lambda: _Acct())
    monkeypatch.setattr(App, "_blocking_banner", fake_banner)
    app._poll_frank()
    assert "lines" not in seen
    assert app.status_message == ""


def test_poll_accepts_matching_users_warn(monkeypatch):
    seen = {}

    def fake_banner(self, lines, min_seconds=0, accept_keys=None):
        seen["lines"] = lines
        return ord(" ")

    class _Acct:
        username = "alice"

    app = _app({"type": "warn",
                "user": "alice",
                "delivery": "statusbar",
                "msg": "Minor infraction.",
                "matched": ""})
    monkeypatch.setattr(session, "get_active_account", lambda: _Acct())
    monkeypatch.setattr(App, "_blocking_banner", fake_banner)
    app._poll_frank()
    assert "lines" in seen


def test_poll_is_throttled():
    app = _app(None)
    app._last_frank_poll = time.monotonic()   # just polled
    app._poll_frank()
    assert app.frank.calls == 0               # inside the interval -> skipped


def test_redact_matched_in_text_is_case_insensitive():
    assert session.redact_matched_in_text("Foo BAR foo", "foo") == "*** BAR ***"
    assert session.redact_matched_in_text("plain", "xyz") == "plain"
    # Longer matches also collapse to fixed *** so word-boundary rules
    # cannot re-fire on a same-length star run.
    assert session.redact_matched_in_text("ran msfconsole here", "msfconsole") == \
        "ran *** here"


def test_redact_infraction_in_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("alpha meterpreter omega", encoding="utf-8")
    assert session.redact_infraction_in_file("meterpreter", p) is True
    assert p.read_text(encoding="utf-8") == "alpha *** omega"


def test_redact_infraction_in_activity(tmp_path, monkeypatch):
    spool = tmp_path / "activity.log"
    spool.write_text(
        '{"ts":1,"user":"alice","kind":"note-save","text":"note-save x\\nmsfconsole"}\n',
        encoding="utf-8")
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVITY_LOG", str(spool))
    assert session.redact_infraction_in_activity("msfconsole") is True
    body = spool.read_text(encoding="utf-8")
    assert "msfconsole" not in body
    assert "***" in body
