"""AI Chat — an on-device general assistant (spec §5), separate from Frank.

This talks to the SAME local model server Frank's sensor uses (bitnet.cpp's
`llama-server` on 127.0.0.1:8080 — frank-ai.service), but is its own trust
domain: an ordinary chat client with no access to Frank's data, verdicts,
config, or enforcement (see ../aiclient.py, ARCHITECTURE.md). One model on the
box, two independent users of it.

On-demand only (spec §5): nothing here runs until the operator opens the screen
and sends a message. Offline-tolerant: if the model server isn't up (dev box, or
an install that hasn't staged the model), it shows a clear notice rather than
failing. The user's messages are also reported to Frank's activity feed, exactly
like notes/screens/launches — observation only, granting no authority over Frank.
"""
from __future__ import annotations

import curses

from .. import activity, labels, theme
from ..aiclient import AssistantClient
from ..app import POP, Screen
from ..ui import LineEdit


class AIChatScreen(Screen):
    title = labels.ASSISTANT
    subtitle = labels.ASSISTANT_SUBTITLE

    def __init__(self, client: AssistantClient | None = None):
        self.client = client or AssistantClient()
        self.edit = LineEdit(limit=200)
        # Visible transcript: list of (speaker, text). `history` is the raw turn
        # list sent to the model (system prompt is added by the client).
        self.transcript: list[tuple[str, str]] = [("", labels.ASSISTANT_INTRO)]
        self.history: list[dict] = []

    def _send(self) -> None:
        text = self.edit.value.strip()
        if not text:
            return
        self.edit = LineEdit(limit=200)
        self.transcript.append((labels.ASSISTANT_PROMPT, text))
        # Report the chat to Frank (observation only — see activity.py). This is
        # the "chat sent" slice of "everything the user does"; it lets Frank's
        # content review see chat just as it sees notes.
        activity.record("chat", text)
        self.history.append({"role": "user", "content": text})
        reply = self.client.chat(self.history)
        if reply is None:
            # Leave the failed turn out of history so a retry isn't poisoned by a
            # half-exchange; show the offline notice instead.
            self.history.pop()
            self.transcript.append(("", labels.ASSISTANT_OFFLINE))
            return
        self.history.append({"role": "assistant", "content": reply})
        self.transcript.append((labels.ASSISTANT, reply))

    def _wrapped_lines(self, width: int) -> list[str]:
        """Flatten the transcript into display lines, wrapped to `width`."""
        out: list[str] = []
        for speaker, text in self.transcript:
            prefix = f"{speaker}: " if speaker else ""
            for para in (prefix + text).splitlines() or [""]:
                if not para:
                    out.append("")
                    continue
                while len(para) > width:
                    cut = para.rfind(" ", 0, width)
                    cut = cut if cut > 0 else width
                    out.append(para[:cut])
                    para = para[cut:].lstrip()
                out.append(para)
            out.append("")   # blank line between turns
        return out

    def draw(self, win, top: int, left: int) -> None:
        h, w = win.getmaxyx()
        width = max(1, w - left - 2)
        # Reserve the last two rows for the input prompt + a spacer.
        body_rows = max(1, h - top - 3)
        lines = self._wrapped_lines(width)
        view = lines[-body_rows:]
        for i, line in enumerate(view):
            try:
                win.addstr(top + i, left, line[:width], theme.attr(theme.PAIR_NORMAL))
            except curses.error:
                pass
        prompt = f"{labels.ASSISTANT_PROMPT}: {self.edit.display()}"
        try:
            win.addstr(h - 2, left, prompt[:width], theme.attr(theme.PAIR_AMBER))
        except curses.error:
            pass

    def status_text(self) -> str:
        return labels.ASSISTANT_HINT

    def handle_key(self, key, app):
        # LineEdit owns the keystrokes: printable chars type into the line,
        # Backspace edits it, Enter submits, Esc cancels. We must NOT treat the
        # generic KEYS_BACK set as "go back" here — it includes 'h', which is a
        # letter the user needs to type. Esc is the one way out (same as the
        # negotiate screen), so typing is never hijacked by navigation.
        result = self.edit.handle(key)
        if result == "cancel":
            return POP
        if result == "submit":
            self._send()
        return None


def screen():
    return AIChatScreen()
