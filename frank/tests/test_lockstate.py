"""Lock-state persistence: the frank->root-enforcer bridge and reboot semantics.

Multi-user (docs/USERS.md): records follow the person, machine locks are
global. The state file carries who holds each lock; the public summary file
carries usernames + expiry timestamps ONLY.
"""
from frankd import lockstate
from frankd.enforcement import Scope, UserEnforcers
from frankd.model import Event, Finding, Severity, Source, Track


def _serious(user="alice"):
    return Finding("r", Track.SECURITY, Severity.SERIOUS,
                   Event(Source.SHELL, "x", user=user), "x")


def _minor(user="alice"):
    return Finding("r", Track.SECURITY, Severity.MINOR,
                   Event(Source.SHELL, "x", user=user), "x")


def _session_locked(user="alice", now=0):
    e = UserEnforcers()
    for _ in range(4):                    # minor -> session-scope lockout
        e.process(_minor(user), now=now)
    assert e.enforcer_for(user).scope() is Scope.SESSION
    return e


def test_write_publishes_active_machine_lock(tmp_path):
    e = UserEnforcers()
    e.process(_serious("alice"), now=0)   # -> machine lockout
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    data = lockstate.read(p)
    assert data["active"] is True
    assert data["scope"] == Scope.MACHINE.value
    assert data["end"] > 0
    assert data["machine"]["user"] == "alice"


def test_write_publishes_session_locks_by_user(tmp_path):
    e = _session_locked("alice")
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    data = lockstate.read(p)
    assert data["active"] is True
    assert data["scope"] == Scope.SESSION.value
    assert "alice" in data["sessions"]
    assert data["machine"] is None


def test_write_publishes_inactive_when_clear(tmp_path):
    e = UserEnforcers()
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    assert lockstate.read(p)["active"] is False


def test_machine_lock_is_restored_after_restart_onto_the_right_user(tmp_path):
    """Reboot cannot escape a machine lock (spec §6) — and after restart the
    lock is still attributed to whoever triggered it."""
    e = UserEnforcers()
    e.process(_serious("alice"), now=100)
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=100)
    fresh = UserEnforcers()               # simulated restart mid-lock
    lockstate.restore_machine_lock(fresh, p, now=200)
    assert fresh.is_locked("alice", 200)
    assert fresh.is_locked("bob", 200)    # machine lock is global
    assert fresh.machine_lockout(200)[0] == "alice"


def test_session_lock_is_dropped_after_restart(tmp_path):
    """A reboot ends the session, so session locks do NOT persist (spec §6)."""
    e = _session_locked("alice")
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    fresh = UserEnforcers()
    lockstate.restore_machine_lock(fresh, p, now=1)
    assert not fresh.is_locked("alice", 1)


def test_expired_machine_lock_not_restored(tmp_path):
    e = UserEnforcers()
    e.process(_serious("alice"), now=0)
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    fresh = UserEnforcers()
    later = e.cfg.hard_ceiling_seconds + 10
    lockstate.restore_machine_lock(fresh, p, now=later)
    assert not fresh.is_locked("alice", later)


def test_public_summary_is_timestamps_names_and_counts_only(tmp_path):
    """The login screen's file discloses when and how many, never why (§6)."""
    import json
    e = _session_locked("alice")
    e.process(_serious("bob"), now=0)
    p = tmp_path / "login.locks"
    lockstate.write_public(p, e, now=0, violations={"alice": 3})
    data = json.loads(p.read_text())
    assert set(data) == {"machine_end", "users", "violations"}
    assert data["machine_end"] > 0
    assert set(data["users"]) == {"alice"}
    assert isinstance(data["users"]["alice"], (int, float))
    # Violations are bare integers per username — no detail.
    assert data["violations"] == {"alice": 3}
    # Nothing about severity, track, rule, or content leaks:
    assert "severity" not in p.read_text()


def test_public_summary_empty_when_clear(tmp_path):
    import json
    p = tmp_path / "login.locks"
    lockstate.write_public(p, UserEnforcers(), now=0)
    data = json.loads(p.read_text())
    assert data == {"machine_end": 0, "users": {}, "violations": {}}
