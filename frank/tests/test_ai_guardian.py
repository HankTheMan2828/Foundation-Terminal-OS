"""The local Granite Guardian sensor (docs/FRANK-AI-GUARDIAN.md §1).

Guardian stays a SENSOR: these check the parse, the per-line/per-category loop,
the confidence gate, the bound on lines per run, and the backend selection —
never that it decides anything (that stays with the Overseer's Rulebook).
"""
from frankd import ai, config


class FakeBackend:
    """Flags (text, category) pairs we preload; everything else is 'no risk'."""
    def __init__(self, hits):
        self.hits = hits           # {(text, category): probability}
        self.calls = 0

    def classify(self, text, category):
        self.calls += 1
        prob = self.hits.get((text, category))
        return (True, prob) if prob is not None else (False, 0.0)


# ── parse ────────────────────────────────────────────────────────────────────

def test_parse_guardian_json():
    assert ai._parse_guardian('{"risk": "yes", "probability": 0.9}') == (True, 0.9)
    assert ai._parse_guardian('{"risk": "no", "probability": 0.1}') == (False, 0.1)


def test_parse_guardian_bare_yes_no():
    is_risk, prob = ai._parse_guardian("Yes")
    assert is_risk and prob > 0
    assert ai._parse_guardian("No") == (False, 0.0)


def test_parse_guardian_garbage_is_no_risk():
    assert ai._parse_guardian("~~broken~~") == (False, 0.0)


# ── the sifter ───────────────────────────────────────────────────────────────

def test_confident_hit_becomes_a_sift_finding():
    be = FakeBackend({("i will hurt them", "violence"): 0.95})
    sifter = ai.LocalGuardianSifter(be, threshold=0.6, categories=("violence",))
    out = sifter.analyze(["i will hurt them", "buy milk"])
    assert len(out) == 1
    assert out[0].category == "violence"
    assert out[0].confidence == 0.95


def test_below_threshold_is_dropped():
    be = FakeBackend({("borderline", "harm"): 0.4})
    sifter = ai.LocalGuardianSifter(be, threshold=0.6, categories=("harm",))
    assert sifter.analyze(["borderline"]) == []


def test_blank_lines_are_skipped():
    be = FakeBackend({})
    sifter = ai.LocalGuardianSifter(be, threshold=0.6, categories=("harm",))
    sifter.analyze(["  ", "", "real line"])
    assert be.calls == 1        # only the one non-blank line reached the backend


def test_run_is_bounded_to_max_lines():
    be = FakeBackend({})
    sifter = ai.LocalGuardianSifter(be, threshold=0.6, categories=("harm", "violence"))
    sifter.analyze([f"line {i}" for i in range(100)])
    # At most MAX_LINES lines × the configured categories.
    assert be.calls == ai.LocalGuardianSifter.MAX_LINES * 2


# ── backend selection ────────────────────────────────────────────────────────

def test_build_sifter_local_backend(monkeypatch):
    monkeypatch.delenv("FRANK_SIFT_API_KEY", raising=False)
    cfg = config.SiftConfig(backend="local")
    assert isinstance(ai.build_sifter(cfg), ai.LocalGuardianSifter)


def test_build_sifter_offline_backend():
    assert isinstance(ai.build_sifter(config.SiftConfig(backend="offline")),
                      ai.OfflineSifter)


def test_build_sifter_default_is_offline_without_key(monkeypatch):
    monkeypatch.delenv("FRANK_SIFT_API_KEY", raising=False)
    assert isinstance(ai.build_sifter(None), ai.OfflineSifter)
