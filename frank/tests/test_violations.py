"""Per-user violation counts: persistence, what increments them, and what the
public login summary discloses (count only — when and how many, never why)."""
from frankd import config
from frankd.daemon import Frank
from frankd.model import Event, Finding, Severity, Source, Track
from frankd.violations import ViolationCounts


def _cfg(tmp_path):
    return config.FrankConfig(
        ledger_path=tmp_path / "ledger",
        incidents_path=tmp_path / "incidents.db",
        events_path=tmp_path / "events.log",
        triage_path=tmp_path / "triage.jsonl",
        verdicts_path=tmp_path / "verdicts.jsonl",
        ipc_socket=tmp_path / "hub.sock",
        login_locks_path=tmp_path / "login.locks",
        violations_path=tmp_path / "violations.json",
    )


def _finding(user, sev=Severity.MINOR):
    return Finding("rule", Track.SECURITY, sev,
                   Event(Source.SHELL, "x", user=user), matched="x")


def test_counts_persist_across_restarts(tmp_path):
    p = tmp_path / "violations.json"
    v = ViolationCounts(p)
    v.increment("alice")
    v.increment("alice")
    v.increment("bob")
    reloaded = ViolationCounts(p)          # a new daemon process
    assert reloaded.counts == {"alice": 2, "bob": 1}


def test_missing_or_corrupt_file_starts_clean(tmp_path):
    assert ViolationCounts(tmp_path / "nope.json").counts == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{broken")
    assert ViolationCounts(bad).counts == {}


def test_warn_and_lockout_count_observe_does_not(tmp_path):
    f = Frank(_cfg(tmp_path))
    f._handle_finding(_finding("alice", Severity.OBSERVE), now=100)
    assert f.violations.counts == {}       # silent observation: no violation
    f._handle_finding(_finding("alice", Severity.MINOR), now=100)   # warn
    assert f.violations.counts == {"alice": 1}
    f._handle_finding(_finding("alice", Severity.SERIOUS), now=100)  # lockout
    assert f.violations.counts == {"alice": 2}


def test_counts_reach_the_public_login_summary(tmp_path):
    import json
    cfg = _cfg(tmp_path)
    f = Frank(cfg)
    f._handle_finding(_finding("alice", Severity.MINOR), now=100)
    f.tick(now=101)
    data = json.loads(cfg.login_locks_path.read_text())
    assert data["violations"] == {"alice": 1}


def test_counts_survive_the_daily_reset(tmp_path):
    """The daily reset clears working escalation memory, never the record."""
    f = Frank(_cfg(tmp_path))
    f._handle_finding(_finding("alice", Severity.MINOR), now=100)
    f.ledger.reset_daily()
    f.enforcers.reset_daily()
    assert f.violations.counts == {"alice": 1}
