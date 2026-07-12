"""The on-device AI assistant screen (screens/aichat.py) + its client wiring.

Checks the assistant actually talks to a model, degrades cleanly when the model
is unreachable, reports chat to Frank's activity feed (observation only), and is
reachable from the Programs menu — it was a hidden dead stub before.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from foundationhub.screens.aichat import AIChatScreen
from foundationhub.screens import programs
from foundationhub import labels
from foundationhub import aiclient


class _FakeClient:
    def __init__(self, reply, *, error: str | None = None):
        self._reply = reply
        self.calls = []
        self.last_error = error

    def chat(self, history):
        self.calls.append(list(history))
        if self._reply is None and self.last_error is None:
            self.last_error = "offline"
        return self._reply


@pytest.fixture
def spool(tmp_path, monkeypatch):
    path = tmp_path / "activity.log"
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVITY_LOG", str(path))
    monkeypatch.setenv("FOUNDATIONHUB_USER", "tester")
    return path


def _submit(screen, text, app=None):
    screen.edit.value = text
    return screen.handle_key(ord("\n"), app)


def test_reply_is_shown_and_tracked_in_history(spool):
    s = AIChatScreen(client=_FakeClient("2 + 2 is 4."))
    _submit(s, "what is 2+2")
    # The model saw the user turn; both turns are in history for context.
    assert s.client.calls == [[{"role": "user", "content": "what is 2+2"}]]
    assert s.history == [
        {"role": "user", "content": "what is 2+2"},
        {"role": "assistant", "content": "2 + 2 is 4."},
    ]
    assert ("You", "what is 2+2") in s.transcript
    assert (labels.ASSISTANT, "2 + 2 is 4.") in s.transcript
    # Thinking line must not linger after the reply lands.
    assert labels.ASSISTANT_THINKING not in [t for _, t in s.transcript]


def test_user_chat_is_reported_to_frank(spool):
    s = AIChatScreen(client=_FakeClient("ok"))
    _submit(s, "hello frank")
    rows = [json.loads(l) for l in spool.read_text().splitlines() if l.strip()]
    assert rows[-1]["kind"] == "chat"
    assert "hello frank" in rows[-1]["text"]


def test_offline_shows_notice_and_does_not_poison_history(spool):
    s = AIChatScreen(client=_FakeClient(None, error="offline"))
    _submit(s, "are you there")
    # The half-exchange is rolled back so a later retry starts clean.
    assert s.history == []
    assert s.transcript[-1][1] == labels.ASSISTANT_OFFLINE


def test_http_error_shows_specific_notice(spool):
    s = AIChatScreen(client=_FakeClient(None, error="http"))
    _submit(s, "hello")
    assert s.history == []
    assert s.transcript[-1][1] == labels.ASSISTANT_ERROR_HTTP


def test_blank_input_is_ignored(spool):
    s = AIChatScreen(client=_FakeClient("should not be called"))
    _submit(s, "   ")
    assert s.client.calls == []
    assert s.history == []


def test_esc_returns_but_letters_type(spool):
    from foundationhub.app import POP
    s = AIChatScreen(client=_FakeClient("x"))
    # 'h' is in the generic back-set but must type into the line, not navigate.
    assert s.handle_key(ord("h"), None) is None
    assert s.edit.value == "h"
    # Esc is the one way out.
    assert s.handle_key(27, None) is POP


def test_assistant_is_on_the_programs_menu():
    labels_on_menu = [item.label for item in programs.screen().menu.items]
    assert labels.ASSISTANT in labels_on_menu


def test_prompt_row_is_above_statusbar(monkeypatch):
    """Input must NOT share the status-bar row (h-2) — that bug hid typing."""
    # theme.attr needs an initialized curses palette; stub it for the layout check.
    monkeypatch.setattr("foundationhub.screens.aichat.theme.attr", lambda *a, **k: 0)
    s = AIChatScreen(client=_FakeClient("x"))

    class _Win:
        def __init__(self):
            self.writes = []
        def getmaxyx(self):
            return 24, 80
        def addstr(self, y, x, text, attr=0):
            self.writes.append((y, x, text))

    win = _Win()
    # draw() places the prompt; Screen.render draws the status bar after this
    # at h-2 — so the prompt must be on h-3.
    s.edit.value = "hello"
    s.draw(win, top=5, left=4)
    assert win.writes, "draw() wrote nothing"
    y, _x, text = win.writes[-1]
    assert y == 24 - 3, f"prompt should be on h-3, got y={y}"
    assert "hello" in text
    assert y != 24 - 2, "prompt must not share the status-bar row"


# ── aiclient unit tests ──────────────────────────────────────────────────────

def test_message_content_string():
    assert aiclient._message_content(
        {"message": {"content": "  hi  "}}) == "hi"


def test_message_content_parts_list():
    choice = {"message": {"content": [
        {"type": "text", "text": "hello "},
        {"type": "text", "text": "world"},
    ]}}
    assert aiclient._message_content(choice) == "hello world"


def test_message_content_empty():
    assert aiclient._message_content({"message": {"content": ""}}) is None
    assert aiclient._message_content({"message": {"content": None}}) is None
    assert aiclient._message_content({}) is None


def test_load_settings_from_env_file(tmp_path, monkeypatch):
    env = tmp_path / "aichat.env"
    env.write_text(
        "FOUNDATIONHUB_AI_URL=http://127.0.0.1:9999/v1/chat/completions\n"
        "FOUNDATIONHUB_AI_MODEL=custom-model\n"
    )
    monkeypatch.setenv("FOUNDATIONHUB_AICHAT_ENV", str(env))
    monkeypatch.delenv("FOUNDATIONHUB_AI_URL", raising=False)
    monkeypatch.delenv("FOUNDATIONHUB_AI_MODEL", raising=False)
    # Re-bind KEY_FILE from the env we just set.
    monkeypatch.setattr(aiclient, "KEY_FILE", Path(env))
    url, model = aiclient._load_settings()
    assert url.endswith(":9999/v1/chat/completions")
    assert model == "custom-model"


def test_complete_offline_returns_error(monkeypatch):
    client = aiclient.AssistantClient(
        url="http://127.0.0.1:1/v1/chat/completions",
        model="x",
    )
    result = client.complete([{"role": "user", "content": "hi"}])
    assert not result.ok
    assert result.error == "offline"


def test_complete_success_parses_reply(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "pong"}}]
            }).encode()

    client = aiclient.AssistantClient(
        url="http://example.test/v1/chat/completions",
        model="x",
    )
    with patch("urllib.request.urlopen", return_value=_Resp()):
        result = client.complete([{"role": "user", "content": "ping"}])
    assert result.ok
    assert result.text == "pong"


def test_no_cloud_fallback_when_local_down(monkeypatch):
    """Local-only: a dead frank-ai.service never phones home to Mistral."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        raise aiclient.urllib.error.URLError("connection refused")

    client = aiclient.AssistantClient(
        url=aiclient.DEFAULT_LOCAL_URL,
        model=aiclient.DEFAULT_LOCAL_MODEL,
        api_key="sk-would-be-ignored",
    )
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.complete([{"role": "user", "content": "hi"}])
    assert not result.ok
    assert result.error == "offline"
    assert calls == [aiclient.DEFAULT_LOCAL_URL]
    assert not any("mistral.ai" in u for u in calls)
