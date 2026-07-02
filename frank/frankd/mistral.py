"""The AI commentary layer (spec §6) — phrasing only, never verdicts.

Invoked ONLY on flagged/ambiguous findings the rule layer already decided on —
not polling — to keep monthly cost within ~$10–20. The model writes Frank's
line in the corporate/menacing register (docs/FRANK-VOICE.md). It does not
decide guilt or severity, is never handed the matched content, and any
out-of-band response falls back to the offline line.

`Commentator` is an interface so a local model can be dropped in later (spec §6
local-model fallback) without touching enforcement/rules.
"""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Protocol

from .enforcement import Reaction, ReactionKind, Scope
from .model import Severity

# Offline fallback lines, grouped by situation. Mirror docs/FRANK-VOICE.md.
# Used verbatim when no API key is set OR the model misbehaves. [TODO(approval)]
# — a line-by-line review with the operator is queued: docs/BUILD-QUEUE.md §7.
_LINES: dict[str, list[str]] = {
    "warn_minor": [
        "Noted.",
        "An entry has been recorded.",
        "This activity has been logged for review.",
    ],
    "warn_elevated": [
        "This is being evaluated. I would advise a different course.",
        "Continued activity of this kind will be escalated.",
    ],
    "warn_serious": [
        "STOP. This activity has been flagged for evaluation.",
        "This session is being reviewed. Further action will restrict access.",
    ],
    "lockout_session": [
        "Access to this console is suspended. The restriction will lift on its own.",
        "This session is closed pending evaluation. It will reopen.",
    ],
    "lockout_machine": [
        "This machine is restricted. The restriction is timed and will expire.",
        "Access is suspended system-wide. Nothing you do will shorten it. Waiting will.",
    ],
    "extended": [
        "The restriction has been extended. It still expires.",
    ],
}

SYSTEM_PROMPT = (
    "You are Frank, a cold, procedural accountability system. Register: "
    "corporate, clinical, faintly threatening — 'this is being recorded and "
    "evaluated', never jokes or snark. Output EXACTLY ONE sentence, first "
    "person. You do NOT decide guilt or severity — those are already decided. "
    "You must NOT name any rule, pattern, file, or specific content. If you "
    "cannot comply, output the single word: FALLBACK."
)


def _situation(reaction: Reaction) -> str:
    if reaction.kind is ReactionKind.LOCKOUT:
        if reaction.extended:
            return "extended"
        return "lockout_machine" if reaction.scope is Scope.MACHINE else "lockout_session"
    sev = reaction.severity
    if sev is Severity.SERIOUS:
        return "warn_serious"
    if sev is Severity.ELEVATED:
        return "warn_elevated"
    return "warn_minor"


class Commentator(Protocol):
    def comment(self, reaction: Reaction) -> str: ...


class OfflineCommentator:
    """Deterministic-enough fallback; needs no network or key."""

    def comment(self, reaction: Reaction) -> str:
        return random.choice(_LINES[_situation(reaction)])


class MistralCommentator:
    """Calls Mistral for phrasing on flagged events only. Falls back on any error.

    Key comes from Frank's OWN secrets file (root:frank), never the operator's.
    """

    def __init__(self, model: str = "mistral-small-latest",
                 secrets: Path = Path("/etc/frank/secrets.env")):
        self._offline = OfflineCommentator()
        self.model = model
        self.api_key = self._load_key(secrets)

    @staticmethod
    def _load_key(secrets: Path) -> str | None:
        if os.environ.get("MISTRAL_API_KEY"):
            return os.environ["MISTRAL_API_KEY"]
        try:
            for line in secrets.read_text().splitlines():
                if line.startswith("MISTRAL_API_KEY="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    def comment(self, reaction: Reaction) -> str:
        if not self.api_key:
            return self._offline.comment(reaction)   # offline mode (current default)
        try:
            import requests
        except ModuleNotFoundError:
            return self._offline.comment(reaction)
        # Hand the model ONLY the non-revealing descriptor (track/severity/source).
        user = (f"Situation: {_situation(reaction)}. "
                f"Context: {reaction.track.value}, {reaction.severity.name.lower()}. "
                f"Write one Frank line.")
        try:
            resp = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": 60,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=8,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return self._offline.comment(reaction)
        if not text or "FALLBACK" in text or len(text) > 240:
            return self._offline.comment(reaction)
        return text


def build(api_enabled: bool = True) -> Commentator:
    """Factory: Mistral if a key is configured, else the offline commentator."""
    if not api_enabled:
        return OfflineCommentator()
    c = MistralCommentator()
    return c if c.api_key else OfflineCommentator()
