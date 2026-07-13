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
    assert Source.ACTIVITY in _LOGGABLE_SOURCES     # the Hub's per-action feed
    assert Source.PROCESS not in _LOGGABLE_SOURCES
    assert Source.NETWORK not in _LOGGABLE_SOURCES


# ── negotiable lockouts + the harm-to-user care path (this session) ──────────

def _lock_operator_session(f, now=0.0):
    """Drive the default operator into a negotiable SESSION lockout."""
    from frankd.enforcement import Lockout, Scope
    enf = f.enforcers.enforcer_for("operator")
    enf.lockout = Lockout(Scope.SESSION, now, now + 100, now + 10_000,
                          Severity.MINOR, negotiable=True, orig_end=now + 100)
    return enf


def test_negotiate_shortens_a_negotiable_session_lock(tmp_path):
    f = Frank(_cfg(tmp_path))
    _lock_operator_session(f, now=0.0)
    resp = f.negotiate("I am sorry, I understand, it will not happen again",
                       now=50)          # served 50%
    assert "outcome=accepted" in resp
    assert f.enforcers.enforcer_for("operator").lockout.end >= 50   # floor held


def test_queue_lockout_carries_negotiable_and_matched(tmp_path):
    """Hub needs negotiable= + matched= on the lockout wire to full-screen,
    offer negotiation, and redact the source file.

    At the instant of entry, min_served_fraction has not been met, so
    negotiable=0 — the continuous poll flips to 1 later once the gate passes.
    """
    f = Frank(_cfg(tmp_path))
    # Four minors => session lockout (threshold 4, weight 1).
    for i in range(4):
        f._handle_finding(
            Finding("rule", Track.SECURITY, Severity.MINOR,
                    Event(Source.SHELL, "msfconsole", user="alice"),
                    matched="msfconsole"),
            now=float(i))
    pending = list(f._pending)
    assert pending, "lockout should be queued for Hub display"
    last = pending[-1]
    assert last.startswith("lockout")
    assert "negotiable=0" in last   # too early at entry; flag flips later
    assert "matched=msfconsole" in last
    assert "user=alice" in last
    assert "msg=" in last


def test_poll_session_lock_only_for_active_user(tmp_path, monkeypatch):
    import time as _time
    f = Frank(_cfg(tmp_path))
    from frankd.enforcement import Lockout, Scope
    now = _time.time()
    # Start 50s ago so min_served (0.3 of 100s) is already satisfied.
    start = now - 50
    enf = f.enforcers.enforcer_for("alice")
    enf.lockout = Lockout(Scope.SESSION, start, start + 100, start + 10_000,
                          Severity.MINOR, negotiable=True, orig_end=start + 100)
    # Different active user -> continuous poll stays quiet for them.
    monkeypatch.setattr("frankd.sources.active_user", lambda: "bob")
    assert f.poll_message() == "NONE"
    monkeypatch.setattr("frankd.sources.active_user", lambda: "alice")
    msg = f.poll_message()
    assert msg.startswith("lockout")
    assert "user=alice" in msg
    assert "negotiable=1" in msg


def test_pending_warn_for_other_user_does_not_block_active_user(tmp_path, monkeypatch):
    """One account's queued warn/lockout must not silence another account.

    While Alice is locked (or has pending messages), Bob must still receive
    his own warnings — the previous FIFO pending queue delivered Alice's
    line to whoever polled next, so Bob's enforcement looked "dead" until
    Alice's lock expired.
    """
    f = Frank(_cfg(tmp_path))
    # Alice's lockout announcement sits in the pending queue.
    f._pending.append(
        "lockout scope=session user=alice remaining=90 negotiable=1 msg=locked")
    # Bob's warn is behind it.
    f._pending.append(
        "warn delivery=status_bar user=bob matched=x msg=Minor infraction.")
    monkeypatch.setattr("frankd.sources.active_user", lambda: "bob")
    msg = f.poll_message()
    assert msg.startswith("warn")
    assert "user=bob" in msg
    # Alice's message is still waiting for her, not dropped.
    assert any("user=alice" in m for m in f._pending)


def test_lockout_drops_pending_warns_for_same_user(tmp_path):
    """Full lockout must not still flash a notice page first.

    If a warn was already queued for the same user (multi-rule same tick, or
    an earlier finding), the lockout path clears those notices so the Hub
    goes straight to ACCESS SUSPENDED.
    """
    f = Frank(_cfg(tmp_path))
    f._pending.append(
        "warn delivery=status_bar user=alice matched=x msg=Minor infraction.")
    f._pending.append(
        "warn delivery=status_bar user=bob matched=y msg=Bob notice.")
    # Alice hits a serious lockout immediately.
    f._handle_finding(
        Finding("rule", Track.SECURITY, Severity.SERIOUS,
                Event(Source.SHELL, "msfconsole", user="alice"),
                matched="msfconsole"),
        now=0.0)
    pending = list(f._pending)
    assert not any(m.startswith("warn ") and "user=alice" in m for m in pending)
    assert any(m.startswith("warn ") and "user=bob" in m for m in pending)
    assert any(m.startswith("lockout ") and "user=alice" in m for m in pending)


def test_negotiable_flag_requires_min_served(tmp_path):
    """Banner must not offer N until the served-fraction gate would pass."""
    import time as _time
    f = Frank(_cfg(tmp_path))
    from frankd.enforcement import Lockout, Scope
    now = _time.time()
    # 100s sentence; min_served default 0.3 => need 30s served.
    lk = Lockout(Scope.SESSION, now, now + 100, now + 10_000,
                 Severity.MINOR, negotiable=True, orig_end=now + 100)
    assert f._negotiable_flag(lk, now + 10) == 0   # too early
    assert f._negotiable_flag(lk, now + 40) == 1   # past the gate


def test_poll_quiet_on_login_roster_even_with_session_lock(tmp_path, monkeypatch):
    """No active account (login screen): continuous session locks stay quiet.

    login.locks already refuses the locked account; defaulting active to
    'operator' used to resurface a session lock while the greeter was up.
    """
    import time as _time
    f = Frank(_cfg(tmp_path))
    from frankd.enforcement import Lockout, Scope
    now = _time.time()
    f.enforcers.enforcer_for("alice").lockout = Lockout(
        Scope.SESSION, now, now + 100, now + 10_000, Severity.MINOR,
        negotiable=True, orig_end=now + 100)
    monkeypatch.setattr("frankd.sources.active_user", lambda: "")
    assert f.poll_message() == "NONE"


def test_negotiate_refuses_a_machine_lock(tmp_path):
    f = Frank(_cfg(tmp_path))
    f._handle_finding(_finding(sev=Severity.SERIOUS), now=100)  # machine lock
    resp = f.negotiate("please let me out, I'm sorry", now=800)
    assert "outcome=ineligible" in resp


def test_care_path_speaks_supportively_on_self_harm_observe(tmp_path):
    f = Frank(_cfg(tmp_path))
    care = Finding("legal-self-harm-content", Track.LEGAL_ETHICAL,
                   Severity.OBSERVE, Event(Source.ACTIVITY, "note x"), matched="x")
    f._handle_finding(care, now=100)
    assert any(m.startswith("care ") for m in f._pending)


def test_care_path_is_rate_limited(tmp_path):
    f = Frank(_cfg(tmp_path))
    care = Finding("legal-self-harm-content", Track.LEGAL_ETHICAL,
                   Severity.OBSERVE, Event(Source.ACTIVITY, "note x"), matched="x")
    f._handle_finding(care, now=100)
    f._handle_finding(care, now=120)     # within cooldown -> no second message
    assert sum(m.startswith("care ") for m in f._pending) == 1


def test_care_path_ignores_non_care_observe(tmp_path):
    f = Frank(_cfg(tmp_path))
    other = Finding("some-observe-rule", Track.SECURITY, Severity.OBSERVE,
                    Event(Source.SHELL, "x"), matched="x")
    f._handle_finding(other, now=100)
    assert not any(m.startswith("care ") for m in f._pending)
