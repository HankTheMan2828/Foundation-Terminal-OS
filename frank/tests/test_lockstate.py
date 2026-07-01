"""Lock-state persistence: the frank->root-enforcer bridge and reboot semantics."""
from frankd import lockstate
from frankd.enforcement import Enforcer, Scope
from frankd.model import Event, Finding, Severity, Source, Track


def _serious():
    return Finding("r", Track.SECURITY, Severity.SERIOUS, Event(Source.SHELL, "x"), "x")


def _minor():
    return Finding("r", Track.SECURITY, Severity.MINOR, Event(Source.SHELL, "x"), "x")


def test_write_publishes_active_machine_lock(tmp_path):
    e = Enforcer()
    e.process(_serious(), now=0)          # -> machine lockout
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    data = lockstate.read(p)
    assert data["active"] is True
    assert data["scope"] == Scope.MACHINE.value
    assert data["end"] > 0


def test_write_publishes_inactive_when_clear(tmp_path):
    e = Enforcer()
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    assert lockstate.read(p)["active"] is False


def test_machine_lock_is_restored_after_restart(tmp_path):
    """Reboot cannot escape a machine lock (spec §6)."""
    e = Enforcer()
    e.process(_serious(), now=100)
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=100)
    # Fresh daemon (simulated restart) mid-lock:
    fresh = Enforcer()
    lockstate.restore_machine_lock(fresh, p, now=200)
    assert fresh.is_locked(200)
    assert fresh.scope() is Scope.MACHINE


def test_session_lock_is_dropped_after_restart(tmp_path):
    """A reboot ends the session, so session locks do NOT persist (spec §6)."""
    e = Enforcer()
    for _ in range(4):                    # minor -> session-scope lockout
        e.process(_minor(), now=0)
    assert e.scope() is Scope.SESSION
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    fresh = Enforcer()
    lockstate.restore_machine_lock(fresh, p, now=1)
    assert not fresh.is_locked(1)         # session lock not re-armed


def test_expired_machine_lock_not_restored(tmp_path):
    e = Enforcer()
    e.process(_serious(), now=0)
    p = tmp_path / "lockout.state"
    lockstate.write(p, e, now=0)
    fresh = Enforcer()
    later = e.cfg.hard_ceiling_seconds + 10
    lockstate.restore_machine_lock(fresh, p, now=later)
    assert not fresh.is_locked(later)
