"""The on-device AI assistant screen (screens/aichat.py) + its client wiring.

Checks the assistant actually talks to a model, degrades cleanly when the model
is unreachable, reports chat to Frank's activity feed (observation only), and is
reachable from the Programs menu — it was a hidden dead stub before.
"""
import json

import pytest

from foundationhub.screens.aichat import AIChatScreen
from foundationhub.screens import programs
from foundationhub import labels


class _FakeClient:
    def __init__(self, reply):
        self._reply = reply
        self.calls = []

    def chat(self, history):
        self.calls.append(list(history))
        return self._reply


@pytest.fixture
def spool(tmp_path, monkeypatch):
    path = tmp_path / "activity.log"
    monkeypatch.setenv("FOUNDATIONHUB_ACTIVITY_LOG", str(path))
    monkeypatch.setenv("FOUNDATIONHUB_USER", "tester")
    return path


def _submit(screen, text):
    screen.edit.value = text
    return screen.handle_key(ord("\n"), None)


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


def test_user_chat_is_reported_to_frank(spool):
    s = AIChatScreen(client=_FakeClient("ok"))
    _submit(s, "hello frank")
    rows = [json.loads(l) for l in spool.read_text().splitlines() if l.strip()]
    assert rows[-1]["kind"] == "chat"
    assert "hello frank" in rows[-1]["text"]


def test_offline_shows_notice_and_does_not_poison_history(spool):
    s = AIChatScreen(client=_FakeClient(None))   # model unreachable
    _submit(s, "are you there")
    # The half-exchange is rolled back so a later retry starts clean.
    assert s.history == []
    assert s.transcript[-1][1] == labels.ASSISTANT_OFFLINE


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
