"""Hub-side negotiation client (docs/FRANK-AI-GUARDIAN.md §4).

The Hub can only ASK; Frank decides. These check the wire parse and that a plea
with spaces survives the line-oriented protocol.
"""
from foundationhub.session import FrankClient


def test_negotiate_parses_frank_response():
    c = FrankClient()
    c._send = lambda line: ("negotiate outcome=accepted removed=25 remaining=35 "
                            "msg=Noted. The restriction has been shortened.")
    r = c.negotiate("I am sorry")
    assert r["outcome"] == "accepted"
    assert r["removed"] == 25
    assert r["remaining"] == 35
    assert r["msg"].startswith("Noted")


def test_negotiate_collapses_multiline_plea_to_one_line():
    sent = {}
    c = FrankClient()

    def fake_send(line):
        sent["line"] = line
        return "negotiate outcome=denied removed=0 remaining=90 msg=Insufficient."
    c._send = fake_send
    c.negotiate("line one\nline two\n  spaced")
    assert "\n" not in sent["line"]
    assert sent["line"].startswith("negotiate line one line two")


def test_negotiate_returns_none_when_offline():
    c = FrankClient()
    c._send = lambda line: None
    assert c.negotiate("x") is None


def test_negotiate_ignores_unexpected_reply():
    c = FrankClient()
    c._send = lambda line: "ERR read-only"
    assert c.negotiate("x") is None
