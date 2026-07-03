"""Frank's voice (spec §6) — how a decided reaction gets phrased for the user.

Operator direction: talking to the user is RULE-BASED — Frank is a primarily
rule-based overseer system (OPEN-QUESTIONS.md §5), and that extends to how it
speaks. The line bank below (`_LINES`, mirroring docs/FRANK-VOICE.md, finalized
via a line-by-line approval review) is Frank's PRIMARY voice — it needs no
key, no network, no model, and behaves identically on every machine, online
or off. AI phrasing (`MistralCommentator`) is an opt-in garnish: it requires
BOTH a key and the root-only `commentary.ai_enabled` flag
(config.CommentaryConfig, default off), and any out-of-band response falls
back to the line bank.

Either way, phrasing only, never verdicts: invoked ONLY on flagged findings
the rule layer already decided on. The model never decides guilt or severity
and is never handed the matched content.

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

# The approved line bank, grouped by situation. Mirrors docs/FRANK-VOICE.md
# (finalized via a line-by-line approval review, 2026-07-02). This is Frank's
# primary voice (rule-based, offline-first); also the fallback whenever the
# opt-in AI phrasing misbehaves.
_LINES: dict[str, list[str]] = {
    "warn_minor": [
        "Minor infraction.",
        "This action has been logged for review.",
    ],
    "warn_elevated": [
        "This is your {n} notice. Your activity is under evaluation. "
        "Continued activity of this kind will be escalated. I would advise "
        "a different course of action.",
    ],
    "warn_serious": [
        "STOP. This activity has been flagged for immediate evaluation. "
        "A temporary penalty may follow.",
    ],
    "lockout_session": [
        "Access to this console is suspended due to {n} minor infractions, "
        "your supervisor has been notified. This user level restriction "
        "will lift on its own in {N} {unit}.",
    ],
    "lockout_machine": [
        "Due to a serious infraction ({Infraction}), this machine is "
        "restricted, your supervisor has been notified, you are now under "
        "official review. The restriction is system wide, operation of "
        "this device will resume in {N} {unit}.",
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


class LineBankCommentator:
    """Frank's primary, rule-based voice: picks from the approved bank for
    the situation the enforcer already decided. Needs no network or key."""

    def comment(self, reaction: Reaction) -> str:
        return random.choice(_LINES[_situation(reaction)])


# Historical name from when the bank was framed as a fallback rather than
# the primary voice; kept so nothing that imported it breaks.
OfflineCommentator = LineBankCommentator


class MistralCommentator:
    """Calls Mistral for phrasing on flagged events only. Falls back on any error.

    Key comes from Frank's OWN secrets file (root:frank), never the operator's.
    """

    def __init__(self, model: str = "mistral-small-latest",
                 secrets: Path = Path("/etc/frank/secrets.env")):
        self._offline = LineBankCommentator()
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


def build(ai_enabled: bool = False) -> Commentator:
    """Factory. The rule-based line bank is the default voice; AI phrasing
    requires the root-only opt-in flag (config.CommentaryConfig.ai_enabled)
    AND a configured key."""
    if not ai_enabled:
        return LineBankCommentator()
    c = MistralCommentator()
    return c if c.api_key else LineBankCommentator()
