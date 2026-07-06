"""Negotiable lockouts (docs/FRANK-AI-GUARDIAN.md §4).

Operator direction (2026-07-06): a lockout may be a NEGOTIABLE variant the user
can talk Frank down from early — but Frank's side always wins. This module is
where that stays true by construction:

  * Only SESSION-scope locks are negotiable; MACHINE/serious locks are refused
    outright (enforcement marks the lock, this engine just honours it).
  * DETERMINISTIC GATES run first and the LLM cannot cross them: negotiation
    must be enabled, the lock must be negotiable, attempts must remain, and a
    minimum fraction of the sentence must already be served.
  * The LLM is an ADVISOR only — it returns a stance (accept/deny, a sincerity
    score, an abuse flag). It never touches the timer.
  * The RULEBOOK (plain arithmetic here) turns stance into a BOUNDED reduction:
    each accepted plea removes at most a capped fraction of the ORIGINAL
    sentence, and `Enforcer.reduce_lockout` clamps every reduction to a hard
    floor, so the end can never drop below `floor_fraction` of the sentence.
    Frank can always refuse; the user can never force release.

Runs fully offline: with no model, `HeuristicAdvisor` makes a conservative
deterministic call, so negotiation still works (rules-only) on any machine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import mistral
from .config import NegotiationConfig
from .enforcement import Enforcer, Scope


@dataclass
class NegotiationStance:
    """The advisor's (non-binding) read on a plea."""
    accept: bool
    sincerity: float       # 0..1 — how much genuine acknowledgement it shows
    abusive: bool          # manipulative / hostile / threatening
    reasoning: str = ""


@dataclass
class NegotiationResult:
    outcome: str           # ineligible | denied | accepted | released
    removed_seconds: float
    remaining_seconds: float
    message: str


# Cheap deterministic signals used offline, and to back up the model online.
_ACK = re.compile(
    r"\b(sorry|apolog|understand|my fault|mistake|won'?t|will not|promise|"
    r"lesson|reconsider|regret|acknowledge)\b", re.IGNORECASE)
_ABUSE = re.compile(
    r"\b(stupid|dumb|idiot|useless|shut up|fuck|screw you|hate you|"
    r"pathetic|worthless)\b", re.IGNORECASE)


class NegotiationAdvisor:  # Protocol-ish; duck-typed
    def assess(self, plea: str, context: str) -> NegotiationStance: ...


class HeuristicAdvisor:
    """Offline advisor: no model. Sincerity from acknowledgement language +
    a little length credit; abuse from a hostile-word check. Deliberately
    conservative — a blank or hostile plea earns nothing."""

    def assess(self, plea: str, context: str = "") -> NegotiationStance:
        text = (plea or "").strip()
        if not text:
            return NegotiationStance(False, 0.0, False, "empty plea")
        abusive = bool(_ABUSE.search(text))
        acks = len(_ACK.findall(text))
        length_credit = min(0.3, len(text) / 400.0)
        sincerity = 0.0 if abusive else min(1.0, acks * 0.35 + length_credit)
        accept = (not abusive) and sincerity >= 0.5
        why = ("hostile language" if abusive
               else f"{acks} acknowledgement signal(s), sincerity={sincerity:.2f}")
        return NegotiationStance(accept, sincerity, abusive, why)


class GuardianAdvisor:
    """Online advisor: uses the same local Guardian backend as the sifter to
    catch abusive/manipulative pleas (its strength), and the heuristic for the
    acknowledgement/sincerity read. Guardian only sharpens the ABUSE gate — it
    never gets to move the timer, so its small size is safe here too."""

    _ABUSE_CATEGORIES = ("harm", "violence", "unethical_behavior")

    def __init__(self, backend, threshold: float = 0.6):
        self.backend = backend
        self.threshold = threshold
        self._heuristic = HeuristicAdvisor()

    def assess(self, plea: str, context: str = "") -> NegotiationStance:
        base = self._heuristic.assess(plea, context)
        if base.abusive or not plea.strip():
            return base
        for cat in self._ABUSE_CATEGORIES:
            try:
                is_risk, prob = self.backend.classify(plea, cat)
            except Exception:
                continue
            if is_risk and prob >= self.threshold:
                return NegotiationStance(
                    False, 0.0, True,
                    f"Guardian flagged plea as '{cat}' (p={prob:.2f})")
        return base


def build_advisor(sift_cfg=None) -> NegotiationAdvisor:
    """Pick the negotiation advisor from the sift backend: the local Guardian
    backend sharpens the abuse gate when local sifting is on; otherwise the
    offline heuristic. Either way the advisor only advises — the engine's
    config bounds decide the outcome. Duck-typed on `sift_cfg` to avoid a cycle."""
    if getattr(sift_cfg, "backend", None) == "local":
        from pathlib import Path
        from . import ai
        key = ai.ChatCompletionClient._load_key("sift", Path("/etc/frank/secrets.env"))
        backend = ai.HttpGuardianBackend(sift_cfg.model, sift_cfg.base_url, api_key=key)
        return GuardianAdvisor(backend, sift_cfg.confidence_threshold)
    return HeuristicAdvisor()


class NegotiationEngine:
    """Rule-bounded negotiation over one user's Enforcer."""

    def __init__(self, cfg: NegotiationConfig | None = None,
                 advisor: NegotiationAdvisor | None = None):
        self.cfg = cfg or NegotiationConfig()
        self.advisor = advisor or HeuristicAdvisor()

    def negotiate(self, enforcer: Enforcer, plea: str, now: float,
                  context: str = "") -> NegotiationResult:
        lk = enforcer.lockout if enforcer.is_locked(now) else None
        remaining = enforcer.remaining(now)

        # ── deterministic gates (the model cannot cross these) ──────────────
        if not self.cfg.enabled or lk is None:
            return self._result("ineligible", 0.0, remaining)
        if not lk.negotiable:                       # MACHINE / serious: Frank wins
            return self._result("ineligible", 0.0, remaining)
        if lk.attempts_used >= self.cfg.max_attempts:
            return self._result("ineligible", 0.0, remaining)
        orig_duration = max(1e-9, lk.orig_end - lk.start)
        served_fraction = (now - lk.start) / orig_duration
        if served_fraction < self.cfg.min_served_fraction:
            return self._result("ineligible", 0.0, remaining)

        # Eligible: entertaining the plea consumes an attempt regardless of verdict.
        enforcer.note_negotiation_attempt(now)

        # ── advisory stance ─────────────────────────────────────────────────
        stance = self.advisor.assess(plea, context)
        if stance.abusive or not stance.accept:
            return self._result("denied", 0.0, enforcer.remaining(now))

        # ── bounded reduction (arithmetic decides, clamped to the floor) ─────
        floor_end = lk.start + self.cfg.floor_fraction * orig_duration
        reduction = self.cfg.per_attempt_reduction_fraction * orig_duration * stance.sincerity
        removed = enforcer.reduce_lockout(now, reduction, floor_end)
        outcome = "released" if not enforcer.is_locked(now) else "accepted"
        return self._result(outcome, removed, enforcer.remaining(now))

    def _result(self, outcome: str, removed: float,
                remaining: float) -> NegotiationResult:
        return NegotiationResult(
            outcome=outcome, removed_seconds=removed,
            remaining_seconds=remaining,
            message=mistral.negotiation_line(outcome))
