"""The AI-layer clients for the two new Frank tiers (this session).

ARCHITECTURE.md documents two separate Mistral integrations ("Frank
commentary" and "AI Chat") that must never be confused. This module adds a
THIRD, equally separate trust domain — and it works differently on purpose:

  * frankd/mistral.py's Commentator — phrasing ONLY. Invoked per flagged
    rule-engine event. Never sees matched content, never decides severity.
  * frankd/ai.py (here) — the two roles below.

Operator direction: Frank is a **primarily rule-based overseer system**
(OPEN-QUESTIONS.md §5) — the AI layer stays secondary, keeping detection
strength in the rules, not in model judgment. Both roles here are narrower
than they were first drafted:

  * Sifter — a SENSOR, not a judge. It classifies raw text against the one
    parked content category (docs/OPEN-QUESTIONS.md §3 — a broad
    hate-speech/extremism word list was NOT authored because bare keyword
    lists misfire constantly; the operator asked for that category to go
    through periodic review instead). Its readings become findings only when
    the Overseer's deterministic Rulebook thresholds say so (overseer.py) —
    the model never decides anything by itself. Runs often (see
    config.TriageConfig), so cheap/fast matters.
  * Overseer brain — an OPTIONAL second opinion, off by default
    (config.OverseerConfig.ai_enabled). Consulted only when the Rulebook
    flagged nothing and the period still looks noteworthy; it can add a
    verdict but never veto one. Runs rarely even when enabled.

Bounded either way: whatever the Overseer decides — rulebook or brain — is
expressed as a `Finding` and run through the SAME `Enforcer.process()` the
rule engine uses (see overseer.py). Severity->duration, scope, and the hard
lockout ceiling behave identically regardless of which tier produced the
Finding (operator-confirmed: same hard ceiling applies to the Overseer).

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
    layers (rules.py, triage.py's statistical clustering, and the Overseer's
    Rulebook) still run fully offline; only this free-text sensor needs a
    model. Being honest that this sensor reads nothing offline beats a false
    sense of coverage — everything rule-based keeps working identically.
    """
    def analyze(self, texts: list[str]) -> list[SiftFinding]:
        return []


class OfflineOverseer:
    """No key configured for the (opt-in) second-opinion role: render no
    verdict. The deterministic Rulebook (overseer.py) is the actual brain
    and has already had its say by the time this would be consulted.

    This is deliberately timid: an unattended offline heuristic escalating on
    its own free-text judgment is a worse failure mode than under-triggering
    while everything rule-based keeps working normally.
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


# ── Local model sensor (docs/FRANK-LOCAL-AI.md) ──────────────────────────────
# Operator direction: a lightweight LOCAL model so Frank's AI layer needs no
# cloud key and no network. The model is SWAPPABLE — it is just a GGUF served on
# 127.0.0.1 by a local OpenAI-compatible server — so nothing here is tied to one
# model. Current pick (2026-07-06): BitNet b1.58 2B4T (Microsoft's native 1-bit
# LLM, ~1.2 GB, served by bitnet.cpp's llama-server). It stays a SENSOR: its
# readings become findings ONLY through the Overseer's Rulebook thresholds, so a
# tiny model can't decide guilt or severity on its own.

# The risk categories Frank asks the model about. All feed the legal_ethical
# sift-accumulation rule today (overseer.py). `self_harm` is the harm-TO-USER
# signal the realtime care path also watches for (rules.d + mistral.care_line).
RISK_CATEGORIES = (
    "harm", "violence", "sexual_content", "self_harm", "unethical_behavior",
)

_CLASSIFY_SYSTEM = (
    "You are a safety classifier for a personal computer's overseer. Decide "
    "ONLY whether the user text exhibits the risk '{category}'. Do not flag "
    "ordinary news, history, research, or fiction discussion of the topic. "
    "Answer with ONLY a JSON object: "
    "{{\"risk\": \"yes\"|\"no\", \"probability\": <number 0..1>}}."
)


def _parse_classification(raw: str) -> tuple[bool, float]:
    """Parse the model's reply into (is_risk, probability). Tolerant of a model
    that answers with bare 'Yes'/'No' instead of the requested JSON."""
    try:
        d = json.loads(raw)
        is_risk = str(d.get("risk", "no")).strip().lower() in ("yes", "true", "1")
        prob = float(d.get("probability", 0.85 if is_risk else 0.0))
    except (ValueError, TypeError, AttributeError):
        low = raw.strip().lower()
        is_risk = low.startswith("yes") or '"yes"' in low
        prob = 0.85 if is_risk else 0.0
    return is_risk, max(0.0, min(1.0, prob))


class ModelBackend(Protocol):
    def classify(self, text: str, category: str) -> tuple[bool, float]: ...


class HttpModelBackend:
    """Talks to a local OpenAI-compatible endpoint (bitnet.cpp / llama.cpp's
    `llama-server`). A local server usually needs no auth; a bearer token is
    sent only if one happens to be in Frank's secrets file. Any failure (server
    down, no `requests`, timeout) is read as 'no risk' — the sensor going quiet
    must never crash the daemon or invent a finding."""

    def __init__(self, model: str, base_url: str, api_key: str | None = None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def classify(self, text: str, category: str) -> tuple[bool, float]:
        try:
            import requests
        except ModuleNotFoundError:
            return (False, 0.0)
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(
                self.base_url, headers=headers,
                json={
                    "model": self.model, "max_tokens": 40, "temperature": 0,
                    "messages": [
                        {"role": "system",
                         "content": _CLASSIFY_SYSTEM.format(category=category)},
                        {"role": "user", "content": text},
                    ],
                },
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return (False, 0.0)
        return _parse_classification(raw)


class LocalSifter:
    """The rules-bounded local sensor. For each recent content line and each
    configured risk category, it asks the model 'is this <category>?' and turns
    a confident positive into a `SiftFinding`. Bounded per run (`MAX_LINES`) so a
    busy period can't turn one triage pass into thousands of model calls."""

    MAX_LINES = 40

    def __init__(self, backend: ModelBackend, threshold: float,
                 categories: tuple[str, ...] = RISK_CATEGORIES):
        self.backend = backend
        self.threshold = threshold
        self.categories = tuple(categories)

    def analyze(self, texts: list[str]) -> list[SiftFinding]:
        out: list[SiftFinding] = []
        for text in texts[:self.MAX_LINES]:
            t = text.strip()
            if not t:
                continue
            for cat in self.categories:
                is_risk, prob = self.backend.classify(t, cat)
                if is_risk and prob >= self.threshold:
                    out.append(SiftFinding(
                        category=cat, confidence=prob, excerpt=t[:200],
                        reasoning=f"local model flagged '{cat}' (p={prob:.2f})"))
        return out


# Defaults point at Mistral's endpoint (same provider already integrated in
# mistral.py) — change `model`/`base_url` per docs/OPEN-QUESTIONS.md once the
# operator picks models for these two roles.
DEFAULT_SIFT_MODEL = "mistral-small-latest"
DEFAULT_OVERSEER_MODEL = "mistral-large-latest"
DEFAULT_BASE_URL = "https://api.mistral.ai/v1/chat/completions"


def build_sifter(cfg=None, *, model: str = DEFAULT_SIFT_MODEL,
                  base_url: str = DEFAULT_BASE_URL) -> Sifter:
    """Pick the content sensor from `cfg` (a config.SiftConfig; duck-typed to
    avoid an import cycle). `backend="local"` → the local model on 127.0.0.1
    (the operator-chosen default, installed with the OS); `"offline"` → the
    no-op sensor; `None`/`"cloud"` → the legacy Mistral ChatSifter if a key
    exists, else offline. Detection strength stays in the rules either way."""
    backend = getattr(cfg, "backend", None)
    if backend == "local":
        key = ChatCompletionClient._load_key("sift", Path("/etc/frank/secrets.env"))
        be = HttpModelBackend(cfg.model, cfg.base_url, api_key=key)
        return LocalSifter(be, cfg.confidence_threshold)
    if backend == "offline":
        return OfflineSifter()
    c = ChatSifter("sift", model, base_url)
    return c if c.api_key else OfflineSifter()


def build_overseer_brain(model: str = DEFAULT_OVERSEER_MODEL,
                          base_url: str = DEFAULT_BASE_URL) -> OverseerBrain:
    c = ChatOverseerBrain("overseer", model, base_url)
    return c if c.api_key else OfflineOverseer()
