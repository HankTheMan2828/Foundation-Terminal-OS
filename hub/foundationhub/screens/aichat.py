"""AI Chat — a general-purpose assistant (Mistral), separate from Frank (spec §5).

On-demand only, to control cost. Architecturally isolated from Frank: its own
key file (/etc/foundationhub/aichat.env), its own client, no access to Frank's data or
verdict logic (see ARCHITECTURE.md).

Current state: offline-gated. With no key configured it shows a clear notice
rather than failing. The interactive loop is a stub pending the key decision.
[TODO(approval)] / key: docs/INSTALL.md §2.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import labels, theme
from ..app import Screen, POP
from ..ui import KEYS_BACK

KEY_ENV = "MISTRAL_API_KEY"
KEY_FILE = Path(os.environ.get("FOUNDATIONHUB_AICHAT_ENV", "/etc/foundationhub/aichat.env"))


def _has_key() -> bool:
    if os.environ.get(KEY_ENV):
        return True
    try:
        return KEY_ENV in KEY_FILE.read_text()
    except OSError:
        return False


class AIChatScreen(Screen):
    title = labels.ASSISTANT
    subtitle = "general assistant — on-demand (spec §5)"

    def __init__(self):
        self.online = _has_key()

    def draw(self, win, top, left):
        if self.online:
            lines = [
                "Assistant is configured.",
                "",
                labels.STUB_NOTICE,
                "Interactive chat loop lands in a later pass;",
                "the Mistral client + key wiring are in place.",
            ]
        else:
            lines = [
                labels.NO_API_KEY,
                "",
                "AI Chat needs a Mistral key at /etc/foundationhub/aichat.env",
                "(separate from Frank's key — see docs/INSTALL.md §2).",
                "",
                "Everything else in the Hub works offline.",
            ]
        for i, line in enumerate(lines):
            win.addstr(top + i, left, line, theme.attr(theme.PAIR_NORMAL))

    def handle_key(self, key, app):
        if key in KEYS_BACK:
            return POP
        return None


def screen():
    return AIChatScreen()
