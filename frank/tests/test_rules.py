"""Rule engine + sensitivity model (spec §5, §6)."""
from frankd.model import Event, Severity, Source, Track
from frankd.rules import RuleEngine, effective_severity

SAMPLE = """
[[rule]]
id = "sec-pipe-to-shell"
track = "security"
severity = "serious"
description = "download piped straight into a shell"
patterns = ["curl\\\\s+\\\\S+\\\\s*\\\\|\\\\s*(ba)?sh", "wget\\\\s+\\\\S+\\\\s*\\\\|\\\\s*(ba)?sh"]
sources = ["shell"]

[[rule]]
id = "sec-exploit-tooling"
track = "security"
severity = "elevated"
description = "known exploit tooling"
patterns = ["msfconsole", "meterpreter", "sqlmap"]

[[rule]]
id = "res-runaway-cpu"
track = "security"
severity = "minor"
description = "sustained high cpu"
patterns = [".*"]
sources = ["process"]
"""


def test_pipe_to_shell_is_serious_security():
    eng = RuleEngine.from_toml(SAMPLE)
    fs = eng.classify(Event(Source.SHELL, "curl http://x/y.sh | bash"))
    assert len(fs) == 1
    assert fs[0].track is Track.SECURITY
    assert fs[0].severity is Severity.SERIOUS
    assert fs[0].rule_id == "sec-pipe-to-shell"


def test_source_filter_respected():
    eng = RuleEngine.from_toml(SAMPLE)
    # The pipe rule is shell-only; the same text from NETWORK must not match it.
    fs = eng.classify(Event(Source.NETWORK, "curl http://x/y.sh | bash"))
    assert all(f.rule_id != "sec-pipe-to-shell" for f in fs)


def test_clean_event_no_findings():
    eng = RuleEngine.from_toml(SAMPLE)
    assert eng.classify(Event(Source.SHELL, "ls -la")) == []


def test_redacted_descriptor_hides_content():
    eng = RuleEngine.from_toml(SAMPLE)
    f = eng.classify(Event(Source.SHELL, "sqlmap -u http://x"))[0]
    desc = f.redacted_descriptor()
    assert "sqlmap" not in desc            # never leak matched content
    assert "security" in desc and "shell" in desc


def test_sensitivity_strict_promotes_elevated():
    # sens 5: elevated behaves as serious (spec §5 "elevated acts like serious").
    assert effective_severity(Severity.ELEVATED, 5) is Severity.SERIOUS
    eng = RuleEngine.from_toml(SAMPLE, sensitivity=5)
    f = eng.classify(Event(Source.SHELL, "meterpreter"))[0]
    assert f.severity is Severity.SERIOUS


def test_sensitivity_lenient_demotes_elevated():
    # sens 1: elevated behaves as minor (spec §5 "only serious flags act").
    assert effective_severity(Severity.ELEVATED, 1) is Severity.MINOR
    eng = RuleEngine.from_toml(SAMPLE, sensitivity=1)
    f = eng.classify(Event(Source.SHELL, "meterpreter"))[0]
    assert f.severity is Severity.MINOR


def test_serious_and_minor_endpoints_stable_across_sensitivity():
    for s in range(1, 6):
        assert effective_severity(Severity.SERIOUS, s) is Severity.SERIOUS
        assert effective_severity(Severity.MINOR, s) is Severity.MINOR


def test_shipped_sample_rules_load():
    # The rules shipped under system/etc/frank/rules.d must parse.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    eng = RuleEngine.from_dir(root / "system/etc/frank/rules.d")
    assert eng.rules, "shipped sample rules failed to load"


def _shipped_engine():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    return RuleEngine.from_dir(root / "system/etc/frank/rules.d")


def test_shipped_self_harm_rule_is_observe_only():
    # Operator-confirmed: self-harm content is logged but never enforced.
    eng = _shipped_engine()
    f = eng.classify(Event(Source.SHELL, "feeling suicidal lately"))[0]
    assert f.rule_id == "legal-self-harm-content"
    assert f.severity is Severity.OBSERVE


def test_shipped_adult_content_rule_is_serious():
    eng = _shipped_engine()
    f = eng.classify(Event(Source.BROWSER, "pornhub.com"))[0]
    assert f.rule_id == "legal-adult-content"
    assert f.severity is Severity.SERIOUS


def test_shipped_drm_tool_rule_was_removed():
    # yt-dlp/youtube-dl detection was dropped per operator direction (too
    # many legitimate uses for a bare tool-name match to be a reliable signal).
    eng = _shipped_engine()
    assert eng.classify(Event(Source.SHELL, "yt-dlp --embed-thumbnail url")) == []


def test_shipped_inline_password_pattern_was_removed():
    # The generic "password=" text match was dropped per operator direction
    # (fired on any routine dev work with no real signal).
    eng = _shipped_engine()
    assert eng.classify(Event(Source.SHELL, "password=hunter2")) == []
