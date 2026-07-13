"""Frank's voice. Operator direction: talking to the user is rule-based —
the approved line bank is the PRIMARY voice; AI phrasing is a double opt-in
(root-only config flag AND a key)."""
from frankd.enforcement import Delivery, Reaction, ReactionKind, Scope
from frankd.mistral import (_LINES, LineBankCommentator, _situation, build,
                            format_line)
from frankd.model import Severity, Track


def _warn(sev=Severity.MINOR, remaining=None):
    return Reaction(ReactionKind.WARN, Delivery.STATUS_BAR, sev, Track.SECURITY,
                    warnings_remaining=remaining)


def _lockout(scope=Scope.SESSION, extended=False, end=100.0):
    return Reaction(ReactionKind.LOCKOUT, Delivery.BANNER, Severity.SERIOUS,
                    Track.SECURITY, scope=scope, lockout_end=end,
                    extended=extended)


def test_default_voice_is_the_rule_based_line_bank():
    assert isinstance(build(), LineBankCommentator)


def test_ai_phrasing_needs_a_key_even_when_opted_in(monkeypatch, tmp_path):
    """ai_enabled alone isn't enough — without a key the bank still speaks.
    (MistralCommentator reads /etc/frank/secrets.env, absent in tests.)"""
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert isinstance(build(ai_enabled=True), LineBankCommentator)


def test_line_bank_covers_every_situation():
    reactions = [_warn(Severity.MINOR), _warn(Severity.ELEVATED),
                 _warn(Severity.SERIOUS), _lockout(Scope.SESSION),
                 _lockout(Scope.MACHINE), _lockout(extended=True)]
    voice = LineBankCommentator()
    for reaction in reactions:
        line = voice.comment(reaction, now=0.0)
        assert line  # every situation produces a non-empty line
        # Placeholders must be filled (no raw {N}/{unit}/{Infraction} left).
        assert "{" not in line


def test_format_line_fills_duration_and_infraction():
    r = _lockout(Scope.MACHINE, end=150.0)
    template = _LINES["lockout_machine"][0]
    out = format_line(template, r, matched="msfconsole", now=0.0)
    assert "msfconsole" in out
    assert "{Infraction}" not in out
    assert "{N}" not in out
    assert "{unit}" not in out


def test_format_line_notice_index_from_warnings_remaining():
    r = _warn(Severity.ELEVATED, remaining=2)
    template = _LINES["warn_elevated"][0]
    out = format_line(template, r, now=0.0)
    assert "{n}" not in out
