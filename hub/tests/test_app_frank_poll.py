"""Regression: the Hub MUST poll frankd and surface what it returns.

This was the bug behind "Frank isn't doing anything" — `FrankClient.poll()`
existed and frankd queued warnings + the harm-to-user care line, but the App
main loop never called poll(), so nothing ever reached the screen. These tests
pin the consumer side: _poll_frank() turns a poll response into a status line,
styles the care line calmly (not as an alarm), and stays quiet on NONE.
"""
import time

from foundationhub.app import App


class _FakeFrank:
    def __init__(self, resp):
        self.resp = resp
        self.calls = 0

    def poll(self):
        self.calls += 1
        return self.resp


def _app(resp):
    # stdscr/root are only touched by run(), not by __init__/_poll_frank.
    app = App(object(), lambda app: object())
    app.frank = _FakeFrank(resp)
    app._last_frank_poll = -1e9   # bypass the throttle
    return app


def test_poll_surfaces_care_line_calmly():
    app = _app({"type": "care",
                "raw": "care msg=You matter. Please reach out to someone close."})
    app._poll_frank()
    assert "reach out to someone" in app.status_message.lower()
    assert app._status_warn is False          # supportive, not an alarm


def test_poll_surfaces_warning_as_alarm():
    app = _app({"type": "warn",
                "raw": "warn delivery=statusbar msg=Flagged: exploit tooling."})
    app._poll_frank()
    assert "Flagged" in app.status_message
    assert app._status_warn is True


def test_poll_none_leaves_status_untouched():
    app = _app({"type": "NONE", "raw": "NONE"})
    app.status_message = ""
    app._poll_frank()
    assert app.status_message == ""


def test_poll_is_throttled():
    app = _app(None)
    app._last_frank_poll = time.monotonic()   # just polled
    app._poll_frank()
    assert app.frank.calls == 0               # inside the interval -> skipped
