"""Enforcement state machine (spec §6). Each test pins one spec invariant."""
from frankd.enforcement import Enforcer, ReactionKind, Scope
from frankd.model import Event, Finding, Severity, Source, Track


def _finding(sev, track=Track.SECURITY):
    return Finding("r", track, sev, Event(Source.SHELL, "x"), matched="x")


def test_serious_locks_immediately_whole_machine():
    """Serious skips straight to action, scope = whole machine (spec §6)."""
    e = Enforcer()
    r = e.process(_finding(Severity.SERIOUS), now=0)
    assert r.kind is ReactionKind.LOCKOUT
    assert r.scope is Scope.MACHINE
    assert e.is_locked(0)


def test_minor_gets_more_warnings_before_lockout():
    """Minor accrues several warnings first (spec §6 'minor gets more')."""
    e = Enforcer()
    warns = 0
    for i in range(10):
        r = e.process(_finding(Severity.MINOR), now=0)
        if r.kind is ReactionKind.WARN:
            warns += 1
        if r.kind is ReactionKind.LOCKOUT:
            break
    assert warns >= 3          # weight 1, threshold 4 -> 3 warnings then lock
    assert e.is_locked(0)
    assert e.scope() is Scope.SESSION   # minor -> this session only (spec §6)


def test_minor_locks_session_scope_only():
    e = Enforcer()
    for _ in range(4):
        r = e.process(_finding(Severity.MINOR), now=0)
    assert r.kind is ReactionKind.LOCKOUT
    assert r.scope is Scope.SESSION


def test_warning_delivery_channel_by_severity():
    """Normal warnings -> status bar; serious -> full-screen banner (spec §6)."""
    e = Enforcer()
    r = e.process(_finding(Severity.MINOR), now=0)
    assert r.kind is ReactionKind.WARN
    assert r.delivery.value == "status_bar"
    e2 = Enforcer()
    r2 = e2.process(_finding(Severity.SERIOUS), now=0)
    assert r2.delivery.value == "banner"


def test_lockout_duration_scales_with_severity():
    minor = Enforcer()
    for _ in range(4):
        minor.process(_finding(Severity.MINOR), now=0)
    serious = Enforcer()
    serious.process(_finding(Severity.SERIOUS), now=0)
    assert serious.remaining(0) > minor.remaining(0)   # severity -> duration


def test_hard_ceiling_is_absolute_even_with_many_extensions():
    """Frank may extend but can NEVER exceed the hard ceiling (spec §6)."""
    e = Enforcer()
    e.process(_finding(Severity.SERIOUS), now=0)
    ceiling = e.cfg.hard_ceiling_seconds
    # Hammer it with serious findings that each try to extend.
    for _ in range(100):
        e.process(_finding(Severity.SERIOUS), now=1)
    assert e.remaining(1) <= ceiling
    assert e.lockout.end <= e.lockout.ceiling_end


def test_extension_lengthens_within_ceiling():
    e = Enforcer()
    e.process(_finding(Severity.SERIOUS), now=0)
    before = e.remaining(0)
    e.process(_finding(Severity.SERIOUS), now=0)
    after = e.remaining(0)
    assert after >= before
    assert after <= e.cfg.hard_ceiling_seconds


def test_lockout_always_expires():
    e = Enforcer()
    e.process(_finding(Severity.SERIOUS), now=0)
    assert e.is_locked(now=0)
    later = e.cfg.hard_ceiling_seconds + 1
    assert not e.is_locked(now=later)     # always eventually clears (spec §6)


def test_override_requires_frank_verification():
    e = Enforcer()
    e.process(_finding(Severity.SERIOUS), now=0)
    assert e.request_override(now=1, verified=False) is False   # no plain bypass
    assert e.is_locked(1)
    assert e.request_override(now=1, verified=True) is True      # verified lifts
    assert not e.is_locked(1)


def test_daily_reset_clears_warnings_but_not_active_lockout():
    """time-of-day -> reset working memory; severity -> lockout. Kept distinct."""
    e = Enforcer()
    # Build up some minor escalation short of a lockout...
    e.process(_finding(Severity.MINOR), now=0)
    e.process(_finding(Severity.MINOR), now=0)
    # ...and separately enter a lockout on the legal/ethical track.
    for _ in range(4):
        e.process(_finding(Severity.MINOR, Track.LEGAL_ETHICAL), now=0)
    assert e.is_locked(0)
    e.reset_daily()
    # Lockout survives the daily reset...
    assert e.is_locked(0)
    # ...but the security-track warning memory was cleared to zero.
    assert e.tracks[Track.SECURITY].score == 0


def test_two_tracks_escalate_independently():
    e = Enforcer()
    e.process(_finding(Severity.MINOR, Track.SECURITY), now=0)
    e.process(_finding(Severity.MINOR, Track.SECURITY), now=0)
    # Legal/ethical track untouched by security-track escalation.
    assert e.tracks[Track.LEGAL_ETHICAL].score == 0
    assert e.tracks[Track.SECURITY].score == 2
