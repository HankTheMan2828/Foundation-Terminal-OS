"""Wiring between the three tiers inside the daemon loop (this session)."""
from frankd import config
from frankd.ai import OverseerVerdict
from frankd.daemon import Frank
from frankd.enforcement import ReactionKind
from frankd.model import Event, Finding, Severity, Source, Track


def _cfg(tmp_path, **overrides):
    cfg = config.FrankConfig(
        ledger_path=tmp_path / "ledger",
        incidents_path=tmp_path / "incidents.db",
        events_path=tmp_path / "events.log",
        triage_path=tmp_path / "triage.jsonl",
        verdicts_path=tmp_path / "verdicts.jsonl",
        ipc_socket=tmp_path / "hub.sock",
        login_locks_path=tmp_path / "login.locks",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _finding(track=Track.SECURITY, sev=Severity.SERIOUS, source=Source.SHELL):
    return Finding("rule", track, sev, Event(source, "x"), matched="x")


class _StubOverseer:
    """Records calls; returns whatever Findings it's told to."""
    def __init__(self, on_serious_result=None, checkin_result=None):
        self.serious_calls = []
        self.checkin_calls = []
        self._on_serious_result = on_serious_result or []
        self._checkin_result = checkin_result or []

    def on_serious_finding(self, finding, now):
        self.serious_calls.append((finding, now))
        return self._on_serious_result

    def check_in(self, now, activity_snapshot=""):
        self.checkin_calls.append((now, activity_snapshot))
        return self._checkin_result


def test_serious_finding_wakes_the_overseer_immediately(tmp_path):
    f = Frank(_cfg(tmp_path))
    stub = _StubOverseer()
    f.overseer = stub
    f._handle_finding(_finding(sev=Severity.SERIOUS), now=100)
    assert len(stub.serious_calls) == 1
    assert stub.serious_calls[0][0].severity is Severity.SERIOUS


def test_non_serious_finding_does_not_wake_the_overseer(tmp_path):
    f = Frank(_cfg(tmp_path))
    stub = _StubOverseer()
    f.overseer = stub
    f._handle_finding(_finding(sev=Severity.MINOR), now=100)
    assert stub.serious_calls == []


def test_wake_on_serious_can_be_disabled(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.overseer.wake_on_serious = False
    f = Frank(cfg)
    stub = _StubOverseer()
    f.overseer = stub
    f._handle_finding(_finding(sev=Severity.SERIOUS), now=100)
    assert stub.serious_calls == []


def test_overseer_findings_flow_through_the_same_handler(tmp_path):
    """A SERIOUS finding causes an immediate review; if the Overseer flags
    something, that too gets a ledger entry + incidents record — the exact
    same pipeline a rule-engine Finding gets."""
    f = Frank(_cfg(tmp_path))
    escalation = Finding("overseer-serious-trigger", Track.SECURITY,
                          Severity.ELEVATED, Event(Source.OVERSEER, "x"), matched="x")
    f.overseer = _StubOverseer(on_serious_result=[escalation])
    f._handle_finding(_finding(sev=Severity.SERIOUS), now=100)
    recorded = f.incidents.since(0)
    assert len(recorded) == 2   # the original SERIOUS finding + the overseer's own
    assert recorded[1]["rule_id"] == "overseer-serious-trigger"


def test_overseer_synthetic_serious_finding_does_not_retrigger_itself(tmp_path):
    """Guard against infinite recursion: a Finding whose source is OVERSEER
    must never itself wake on_serious_finding again, even if its severity is
    SERIOUS."""
    f = Frank(_cfg(tmp_path))
    stub = _StubOverseer()
    f.overseer = stub
    synthetic = Finding("overseer-checkin", Track.SECURITY, Severity.SERIOUS,
                         Event(Source.OVERSEER, "x"), matched="x")
    f._handle_finding(synthetic, now=100)
    assert stub.serious_calls == []


def test_triage_runs_on_its_configured_interval(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.triage.interval_seconds = 10
    f = Frank(cfg)
    f._last_triage_run = 0.0
    assert f.triage_store.latest() is None
    f.tick(now=5)                      # not yet due
    assert f.triage_store.latest() is None
    f.tick(now=11)                     # interval elapsed
    assert f.triage_store.latest() is not None


def test_overseer_checkin_runs_on_its_configured_interval(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.overseer.checkin_interval_seconds = 10
    f = Frank(cfg)
    f._last_overseer_checkin = 0.0
    stub = _StubOverseer()
    f.overseer = stub
    f.tick(now=5)
    assert stub.checkin_calls == []
    f.tick(now=11)
    assert len(stub.checkin_calls) == 1


def test_activity_snapshot_reflects_lock_state(tmp_path):
    f = Frank(_cfg(tmp_path))
    snap = f._activity_snapshot(now=100)
    assert "lockout: none" in snap
    f.enforcers.process(_finding(sev=Severity.SERIOUS), now=100)
    snap2 = f._activity_snapshot(now=100)
    assert "lockout: active scope=machine" in snap2


def test_findings_are_recorded_per_user(tmp_path):
    """Records follow the person (docs/USERS.md): the incident entry carries
    the logical user, and enforcement state is keyed by it."""
    f = Frank(_cfg(tmp_path))
    ev = Event(Source.SHELL, "x", user="alice")
    f._handle_finding(Finding("rule", Track.SECURITY, Severity.MINOR, ev, "x"),
                      now=100)
    entry = f.incidents.since(0)[0]
    assert entry["user"] == "alice"
    assert "alice" in f.enforcers.users
    assert not f.enforcers.enforcer_for("bob").is_locked(100)


def test_default_posture_is_fully_rule_based(tmp_path):
    """Operator direction: Frank is a primarily rule-based overseer system
    (OPEN-QUESTIONS.md §5). Out of the box the daemon wires NO AI brain into
    the Overseer (rulebook only) and speaks from the approved line bank —
    no network needed anywhere in the loop."""
    from frankd.mistral import LineBankCommentator
    f = Frank(_cfg(tmp_path))
    assert f.overseer.brain is None
    assert f.overseer.rulebook is not None
    assert isinstance(f.commentator, LineBankCommentator)


def test_ai_second_opinion_is_opt_in_via_root_config(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.overseer.ai_enabled = True
    f = Frank(cfg)
    # No key in the test environment -> the safe OfflineOverseer, but the
    # consult path now exists at all, which it doesn't by default.
    assert f.overseer.brain is not None


def test_only_content_bearing_sources_are_persisted_to_the_raw_eventlog():
    """tick() gates eventlog.record() on this set -- process/network events
    are numeric/destination signals with no text for a content review to
    read, so persisting them would be pure volume (see daemon.py)."""
    from frankd.daemon import _LOGGABLE_SOURCES
    assert Source.SHELL in _LOGGABLE_SOURCES
    assert Source.BROWSER in _LOGGABLE_SOURCES
    assert Source.PROCESS not in _LOGGABLE_SOURCES
    assert Source.NETWORK not in _LOGGABLE_SOURCES
