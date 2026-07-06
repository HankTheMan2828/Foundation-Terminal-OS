"""Enforcement-side negotiable-lockout primitives (docs/FRANK-AI-GUARDIAN.md §4).

The floor clamp lives in the enforcer, next to the ceiling it already owns —
these check the flag is set correctly on entry and that reduce_lockout can never
cross the floor or run the clock backwards.
"""
from frankd.config import EnforcementConfig
from frankd.enforcement import Enforcer, Scope
from frankd.model import Event, Finding, Severity, Source, Track


def test_session_lockout_is_negotiable_machine_is_not():
    enf = Enforcer()
    for _ in range(4):
        r = enf.process(Finding("r", Track.SECURITY, Severity.MINOR,
                                Event(Source.SHELL, "x"), matched="x"), now=0)
    assert r.scope is Scope.SESSION
    assert enf.lockout.negotiable is True

    enf2 = Enforcer()
    r2 = enf2.process(Finding("r", Track.SECURITY, Severity.SERIOUS,
                              Event(Source.SHELL, "x"), matched="x"), now=0)
    assert r2.scope is Scope.MACHINE
    assert enf2.lockout.negotiable is False


def test_reduce_lockout_respects_the_floor():
    enf = Enforcer(EnforcementConfig())
    enf.process(Finding("r", Track.SECURITY, Severity.SERIOUS,
                        Event(Source.SHELL, "x"), matched="x"), now=0)
    # machine lock; end = base 900. Reduce by 1000 with a floor at 400.
    removed = enf.reduce_lockout(now=100, seconds=1000, floor_end=400)
    assert enf.lockout.end == 400
    assert removed == 500        # 900 -> 400


def test_reduce_lockout_never_runs_clock_backwards():
    enf = Enforcer()
    enf.process(Finding("r", Track.SECURITY, Severity.SERIOUS,
                        Event(Source.SHELL, "x"), matched="x"), now=0)
    # floor below 'now' -> can only reduce down to now, then the lock lifts.
    removed = enf.reduce_lockout(now=500, seconds=10_000, floor_end=0)
    assert not enf.is_locked(500)
    assert removed == 400        # end was 900, clamped to now=500


def test_reduce_lockout_noop_when_unlocked():
    enf = Enforcer()
    assert enf.reduce_lockout(now=0, seconds=100, floor_end=0) == 0.0
