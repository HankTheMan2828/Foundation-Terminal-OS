"""The AI-layer clients for the two new Frank tiers (this session).

ARCHITECTURE.md documents two separate Mistral integrations ("Frank
commentary" and "AI Chat") that must never be confused. This module adds a
THIRD, equally separate trust domain — and it works differently on purpose:

  * frankd/mistral.py's Commentator — phrasing ONLY. Invoked per flagged
    rule-engine event. Never sees matched content, never decides severity.
  * frankd/ai.py (here) — DOES make judgment calls. This is the deliberate
    exception the operator asked for this session: a scheduled/periodic
    AI-driven review sitting ABOVE the realtime rule engine, for exactly the
    gap the rule layer left open on purpose (docs/OPEN-QUESTIONS.md §3 —
    a broad hate-speech/extremism word list was NOT authored because bare
    keyword lists misfire constantly; the operator asked for that category to
    go through periodic review instead).

This is bounded, not a loophole: whatever the Overseer decides is expressed as
a `Finding` and run through the SAME `Enforcer.process()` the rule engine
uses (see overseer.py). Severity->duration, scope, and the hard lockout
ceiling behave identically regardless of which tier produced the Finding —
the Overseer cannot exceed invariants that already bind Frank as a whole
(operator-confirmed this session: same hard ceiling applies to the Overseer).

Two roles, one wire shape:
  * Sifter   — classifies a batch of raw text against the parked content
    categories. Runs often (see config.TriageConfig), so cheap/fast matters.
  * Overseer brain — reasons over an already-organized digest (+ optionally a
    directly-queried raw window) and returns one verdict. Runs rarely (a
    couple of times a day, or on a SERIOUS trigger), so a stronger model is
    affordable even on a tight budget.

Model choice is NOT hardcoded — see docs/OPEN-QUESTIONS.md for researched
recommendations (kept as an open operator decision, same as sensitivity was).
`ChatCompletionClient` below speaks the OpenAI/Mistral-style
`/v1/chat/completions` shape (the same shape frankd/mistral.py already
integrates against) so today's client works with Mistral or any
OpenAI-compatible endpoint without new dependencies. A provider with a
different wire shape (e.g. Anthropic's Messages API) is a second class behind
the same Protocol, not a rewrite of this module.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .model import Severity, Track

_TRACK = {t.value: t for t in Track}
_SEVERITY = {s.name.lower(): s for s in Severity}


@dataclass
class SiftFinding:
    """One candidate observation from the sifter's content review.

    Deliberately NOT a `Finding` (frankd/model.py) — it hasn't been decided
    yet. It is raw material the Overseer weighs at its next check-in, same as
    the rule engine's stats. See triage.py.
    """
    category: str          # e.g. "hate_speech_extremism"
    confidence: float      # 0..1, the model's own stated confidence
    excerpt: str           # the text that triggered it (frank-only)
    reasoning: str


@dataclass
class OverseerVerdict:
    """What the Overseer decided at one check-in. `flagged=False` is the
    common case — most check-ins find nothing worth escalating.

    Deliberately does NOT let the model pick warn-vs-lockout directly: the
    Overseer decides WHAT to flag (track + severity), same lever the rule
    engine has, and the SAME Enforcer.process() then derives the actual
    reaction (warn/lockout, scope, duration) from that severity — exactly as
    it would for a rule-engine Finding. This is what keeps "same hard ceiling
    applies to the Overseer" true by construction rather than by convention:
    there is no second code path that could special-case its own limits.
    """
    flagged: bool
    track: Track | None
    severity: Severity | None
    reasoning: str


class Sifter(Protocol):
    def analyze(self, texts: list[str]) -> list[SiftFinding]: ...


class OverseerBrain(Protocol):
    def decide(self, context: str) -> OverseerVerdict: ...


_SIFT_SYSTEM_PROMPT = (
    "You are a content-safety classifier for a personal computer's security "
    "system. You are given a batch of raw text lines (shell history, browser "
    "activity). Flag ONLY the categories explicitly listed below — do not "
    "invent new categories, and do not flag ordinary news/history/fiction "
    "discussion of these topics. Categories: hate_speech_extremism (content "
    "advocating hatred or violence against a group, or extremist "
    "recruitment/propaganda material). Respond with a JSON array; each "
    "element: {\"category\": str, \"confidence\": 0..1, \"line\": the exact "
    "flagged line, \"reasoning\": one sentence}. Empty array if nothing "
    "qualifies. Output ONLY the JSON array, nothing else."
)

_OVERSEER_SYSTEM_PROMPT = (
    "You are the overseer tier of a personal computer's security system. You "
    "receive an organized digest of recent activity (statistics + any "
    "sifted content observations, and current activity) and decide whether "
    "escalation is warranted. You are NOT the first line of defense — a "
    "realtime rule engine already handles clear-cut cases; you exist for "
    "judgment calls on ambiguous or accumulating patterns. You do not choose "
    "warn vs. lockout directly — you choose a track and severity, and the "
    "same enforcement machinery the rule engine uses derives the actual "
    "reaction from that. Respond with ONLY a JSON object: "
    "{\"flagged\": bool, "
    "\"track\": \"security\"|\"legal_ethical\"|null, "
    "\"severity\": \"observe\"|\"minor\"|\"elevated\"|\"serious\"|null, "
    "\"reasoning\": str}. Use flagged=false unless the evidence genuinely "
    "warrants action — false positives cost the user's trust."
)


class OfflineSifter:
    """No key configured: cannot do semantic content classification.

    Mirrors mistral.py's offline-mode philosophy — the realtime/structured
    layers (rules.py, and triage.py's own statistical clustering) still run
    fully offline; only the free-text judgment call needs a model. Being
    honest that this tier is a no-op offline beats a false sense of coverage.
    """
    def analyze(self, texts: list[str]) -> list[SiftFinding]:
        return []


class OfflineOverseer:
    """No key configured: fall back to a conservative, purely statistical
    verdict computed by the caller (triage.py hands us the summary text; we
    have no model to reason over it further, so we default to inaction).

    This is deliberately timid: an unattended offline heuristic escalating on
    its own judgment is a worse failure mode than under-triggering while
    everything the rule engine already covers keeps working normally.
    """
    def decide(self, context: str) -> OverseerVerdict:
        return OverseerVerdict(False, None, None,
                                "offline mode: no model configured, no verdict rendered")


class ChatCompletionClient:
    """Speaks the OpenAI/Mistral-style chat-completions shape.

    Same secrets file as mistral.py so the operator manages one credential
    surface, but a distinct env var / key line per role so spend is
    attributable per tier (spec's cost-attribution intent, extended to the
    two new tiers).
    """
    def __init__(self, role: str, model: str, base_url: str,
                 secrets: Path = Path("/etc/frank/secrets.env")):
        self.role = role
        self.model = model
        self.base_url = base_url
        self.api_key = self._load_key(role, secrets)

    @staticmethod
    def _load_key(role: str, secrets: Path) -> str | None:
        env_var = f"FRANK_{role.upper()}_API_KEY"
        if os.environ.get(env_var):
            return os.environ[env_var]
        try:
            for line in secrets.read_text().splitlines():
                if line.startswith(f"{env_var}="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    def _complete(self, system: str, user: str) -> str | None:
        if not self.api_key:
            return None
        try:
            import requests
        except ModuleNotFoundError:
            return None
        try:
            resp = requests.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None


class ChatSifter(ChatCompletionClient):
    def analyze(self, texts: list[str]) -> list[SiftFinding]:
        if not texts:
            return []
        user = "\n".join(f"- {t}" for t in texts)
        raw = self._complete(_SIFT_SYSTEM_PROMPT, user)
        if not raw:
            return []
        try:
            items = json.loads(raw)
        except ValueError:
            return []
        out = []
        for it in items if isinstance(items, list) else []:
            try:
                out.append(SiftFinding(
                    category=str(it["category"]),
                    confidence=float(it.get("confidence", 0.5)),
                    excerpt=str(it.get("line", "")),
                    reasoning=str(it.get("reasoning", "")),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out


class ChatOverseerBrain(ChatCompletionClient):
    def decide(self, context: str) -> OverseerVerdict:
        raw = self._complete(_OVERSEER_SYSTEM_PROMPT, context)
        if not raw:
            return OfflineOverseer().decide(context)
        try:
            data = json.loads(raw)
            flagged = bool(data.get("flagged", False))
            track = _TRACK.get(data.get("track"))
            severity = _SEVERITY.get(str(data.get("severity", "")).lower())
            reasoning = str(data.get("reasoning", ""))
        except (ValueError, AttributeError):
            return OfflineOverseer().decide(context)
        if flagged and (track is None or severity is None):
            # Model said "flag" but didn't give us enough to act on —
            # fail closed (no Finding) rather than guessing track/severity.
            return OverseerVerdict(False, None, None,
                                    "flagged but incomplete track/severity; discarded")
        return OverseerVerdict(flagged, track, severity, reasoning)


# Defaults point at Mistral's endpoint (same provider already integrated in
# mistral.py) — change `model`/`base_url` per docs/OPEN-QUESTIONS.md once the
# operator picks models for these two roles.
DEFAULT_SIFT_MODEL = "mistral-small-latest"
DEFAULT_OVERSEER_MODEL = "mistral-large-latest"
DEFAULT_BASE_URL = "https://api.mistral.ai/v1/chat/completions"


def build_sifter(model: str = DEFAULT_SIFT_MODEL,
                  base_url: str = DEFAULT_BASE_URL) -> Sifter:
    c = ChatSifter("sift", model, base_url)
    return c if c.api_key else OfflineSifter()


def build_overseer_brain(model: str = DEFAULT_OVERSEER_MODEL,
                          base_url: str = DEFAULT_BASE_URL) -> OverseerBrain:
    c = ChatOverseerBrain("overseer", model, base_url)
    return c if c.api_key else OfflineOverseer()
