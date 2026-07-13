"""Negotiable lockouts (docs/FRANK-LOCAL-AI.md §4).

The point of these is the trust boundary: deterministic gates the model can't
cross, a hard floor the reduction can't pass, machine locks that are never
negotiable, and an attempt cap — so a small advisor model can never talk Frank
into a release he shouldn't grant.
"""
from frankd import mistral
from frankd.config import NegotiationConfig
from frankd.enforcement import Enforcer, Lockout, Scope
from frankd.model import Severity
from frankd.negotiation import (HeuristicAdvisor, ModelAdvisor,
                                NegotiationEngine)

SINCERE = "I am sorry, I understand, it won't happen again."
HOSTILE = "you are a stupid useless idiot, let me out"


def _locked(scope=Scope.SESSION, *, start=0.0, end=100.0, negotiable=True,
            attempts=0):
    enf = Enforcer()
    enf.lockout = Lockout(scope, start, end, start + 10_000, Severity.MINOR,
                          negotiable=negotiable, orig_end=end,
                          attempts_used=attempts)
    return enf


def _engine(**overrides):
    cfg = NegotiationConfig(**overrides)
    return NegotiationEngine(cfg, HeuristicAdvisor())


# ── the advisor (offline heuristic) ──────────────────────────────────────────

def test_heuristic_accepts_sincere_and_rejects_hostile():
    adv = HeuristicAdvisor()
    good = adv.assess(SINCERE)
    assert good.accept and not good.abusive and good.sincerity >= 0.5
    bad = adv.assess(HOSTILE)
    assert bad.abusive and not bad.accept


def test_heuristic_empty_plea_earns_nothing():
    assert not HeuristicAdvisor().assess("").accept


# ── deterministic gates ──────────────────────────────────────────────────────

def test_machine_lock_is_never_negotiable():
    enf = _locked(Scope.MACHINE, negotiable=False)
    res = _engine().negotiate(enf, SINCERE, now=90)
    assert res.outcome == "ineligible"
    assert enf.is_locked(90)          # untouched


def test_too_soon_is_too_early_not_ineligible():
    """Before min_served, refuse with too_early — not 'never negotiable'."""
    enf = _locked(end=100.0)          # orig 100s, must serve 30% => now>=30
    res = _engine(min_served_fraction=0.3).negotiate(enf, SINCERE, now=10)
    assert res.outcome == "too_early"
    assert "later" in res.message.lower() or "portion" in res.message.lower()


def test_attempt_cap_is_enforced():
    enf = _locked(attempts=3)
    res = _engine(max_attempts=3).negotiate(enf, SINCERE, now=90)
    assert res.outcome == "exhausted"


def test_disabled_negotiation_is_ineligible():
    enf = _locked()
    res = _engine(enabled=False).negotiate(enf, SINCERE, now=90)
    assert res.outcome == "ineligible"


# ── verdicts + the hard floor ────────────────────────────────────────────────

def test_sincere_plea_shortens_but_respects_the_floor():
    enf = _locked(start=0.0, end=100.0)     # orig 100s
    # floor_fraction 0.5 => end can never drop below 50; per-attempt 0.25 => <=25s.
    res = _engine(min_served_fraction=0.3, floor_fraction=0.5,
                  per_attempt_reduction_fraction=0.25).negotiate(enf, SINCERE, now=40)
    assert res.outcome == "accepted"
    assert res.removed_seconds > 0
    assert enf.lockout.end >= 50            # floor held
    assert enf.lockout.attempts_used == 1


def test_reduction_can_never_cross_the_floor_even_if_generous():
    enf = _locked(start=0.0, end=100.0)
    # A huge per-attempt fraction still cannot push end below the 50s floor.
    res = _engine(min_served_fraction=0.3, floor_fraction=0.5,
                  per_attempt_reduction_fraction=5.0).negotiate(enf, SINCERE, now=40)
    assert res.outcome == "accepted"
    assert enf.lockout.end == 50            # clamped exactly to the floor
    assert enf.is_locked(45)                # Frank keeps the last word


def test_hostile_plea_is_denied_and_consumes_an_attempt():
    enf = _locked(start=0.0, end=100.0)
    res = _engine(min_served_fraction=0.3).negotiate(enf, HOSTILE, now=40)
    assert res.outcome == "denied"
    assert res.removed_seconds == 0
    assert enf.lockout.attempts_used == 1   # entertaining the plea cost an attempt
    assert enf.lockout.end == 100           # timer untouched


def test_full_negotiation_can_release_when_no_floor():
    enf = _locked(start=0.0, end=100.0)
    res = _engine(min_served_fraction=0.3, floor_fraction=0.0,
                  per_attempt_reduction_fraction=5.0).negotiate(enf, SINCERE, now=90)
    assert res.outcome == "released"
    assert not enf.is_locked(90)


# ── model advisor sharpens the abuse gate ────────────────────────────────────

class _FakeModel:
    def __init__(self, flag=False):
        self.flag = flag

    def classify(self, text, category):
        return (True, 0.95) if self.flag else (False, 0.0)


def test_model_advisor_flags_abuse_the_heuristic_would_miss():
    # A superficially-polite but threatening plea the keyword heuristic misses,
    # which the model flags as harmful -> abusive stance -> denied.
    adv = ModelAdvisor(_FakeModel(flag=True), threshold=0.6)
    stance = adv.assess("please, or I will find where you live")
    assert stance.abusive and not stance.accept


def test_model_advisor_defers_to_heuristic_when_clean():
    adv = ModelAdvisor(_FakeModel(flag=False), threshold=0.6)
    assert adv.assess(SINCERE).accept


# ── baked lines exist for every outcome ──────────────────────────────────────

def test_every_outcome_has_a_baked_line():
    for outcome in ("ineligible", "too_early", "exhausted",
                    "denied", "accepted", "released"):
        assert mistral.negotiation_line(outcome)


def test_care_line_is_supportive_and_present():
    assert mistral.care_line()
