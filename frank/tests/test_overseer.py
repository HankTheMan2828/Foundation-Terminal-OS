"""Main Frank / the Overseer.

Operator direction: Frank is a primarily rule-based overseer system
(OPEN-QUESTIONS.md §5). Verdicts come from the deterministic Rulebook
(identical online/offline); the AI brain is an opt-in second opinion that is
only consulted when the rulebook flagged nothing — and either way the result
flows through the SAME Enforcer path as a rule-engine Finding."""
import json

from frankd import ai, config
from frankd.enforcement import Enforcer, ReactionKind
from frankd.eventlog import EventLog
from frankd.incidents import IncidentStore
from frankd.model import Event, Finding, Severity, Source, Track
from frankd.overseer import Overseer, Rulebook, VerdictLog
from frankd.triage import TriageReport, TriageStore


def _finding(track=Track.SECURITY, sev=Severity.SERIOUS, source=Source.SHELL,
             rule_id="r"):
    return Finding(rule_id, track, sev, Event(source, "x"), matched="x")


def _sift(conf=0.9, category="hate_speech_extremism"):
    return ai.SiftFinding(category=category, confidence=conf, excerpt="…",
                          reasoning="test")


def _report(ts=50, sift=(), counts=None, max_severity=None):
    return TriageReport(ts=ts, window_start=ts - 50, window_end=ts,
                        incident_counts=counts or {},
                        max_severity=max_severity,
                        sift_findings=list(sift))


class _StubBrain:
    def __init__(self, verdict):
        self.verdict = verdict
        self.contexts_seen = []

    def decide(self, context):
        self.contexts_seen.append(context)
        return self.verdict


def _overseer(tmp_path, brain=None, rulebook=None):
    triage = TriageStore(tmp_path / "triage.jsonl")
    incidents = IncidentStore(tmp_path / "incidents.db")
    eventlog = EventLog(tmp_path / "events.log")
    verdicts = VerdictLog(tmp_path / "verdicts.jsonl")
    return Overseer(triage, incidents, eventlog, verdicts,
                    rulebook=rulebook, brain=brain)


# ── the deterministic rulebook ──────────────────────────────────────────────

def test_quiet_period_flags_nothing():
    verdict = Rulebook().checkin_verdict([], [])
    assert verdict.flagged is False


def test_sift_rule_severity_scales_with_confident_count():
    rb = Rulebook()
    one = rb.checkin_verdict([_report(sift=[_sift()])], [])
    assert (one.flagged, one.track, one.severity) == (
        True, Track.LEGAL_ETHICAL, Severity.MINOR)
    two = rb.checkin_verdict([_report(sift=[_sift(), _sift()])], [])
    assert two.severity is Severity.ELEVATED
    five = rb.checkin_verdict([_report(sift=[_sift()] * 5)], [])
    assert five.severity is Severity.SERIOUS


def test_sift_rule_ignores_low_confidence_readings():
    """The sifter is a sensor, not a judge: readings under the confidence
    threshold never become a verdict, no matter how many accumulate."""
    rb = Rulebook()
    verdict = rb.checkin_verdict([_report(sift=[_sift(conf=0.4)] * 10)], [])
    assert verdict.flagged is False


def test_sift_rule_accumulates_across_reports():
    rb = Rulebook()
    reports = [_report(ts=10, sift=[_sift()]), _report(ts=20, sift=[_sift()])]
    verdict = rb.checkin_verdict(reports, [])
    assert verdict.severity is Severity.ELEVATED


def _incident(rule_id="r1", track="security", severity="MINOR"):
    return {"rule_id": rule_id, "track": track, "severity": severity}


def test_slow_burn_rule_fires_on_scattered_same_track_incidents():
    rb = Rulebook()
    incidents = [_incident(rule_id=f"r{i}") for i in range(12)]
    verdict = rb.checkin_verdict([], incidents)
    assert (verdict.flagged, verdict.track, verdict.severity) == (
        True, Track.SECURITY, Severity.ELEVATED)


def test_slow_burn_rule_below_threshold_stays_quiet():
    verdict = Rulebook().checkin_verdict([], [_incident()] * 11)
    assert verdict.flagged is False


def test_slow_burn_ignores_observe_tier_and_overseer_own_findings():
    """OBSERVE stays outside the punitive pipeline (spec) and the Overseer's
    own prior verdicts must never feed the next one (no feedback loop)."""
    rb = Rulebook()
    incidents = ([_incident(severity="OBSERVE")] * 12
                 + [_incident(rule_id="overseer-checkin")] * 12)
    assert rb.checkin_verdict([], incidents).flagged is False


def test_checkin_picks_the_most_severe_fired_rule():
    rb = Rulebook()
    reports = [_report(sift=[_sift()] * 5)]           # -> SERIOUS
    incidents = [_incident(rule_id=f"r{i}") for i in range(12)]  # -> ELEVATED
    verdict = rb.checkin_verdict(reports, incidents)
    assert verdict.severity is Severity.SERIOUS


def test_burst_rule_escalates_a_serious_finding_amid_a_spray():
    rb = Rulebook()
    recent = [_incident(rule_id=f"r{i % 4}") for i in range(10)]
    verdict = rb.serious_verdict(_finding(), recent)
    assert (verdict.flagged, verdict.severity) == (True, Severity.SERIOUS)
    assert verdict.track is Track.SECURITY


def test_burst_rule_stays_quiet_for_an_isolated_serious_finding():
    verdict = Rulebook().serious_verdict(_finding(), recent=[])
    assert verdict.flagged is False


def test_burst_rule_requires_distinct_rules_not_just_volume():
    """One noisy rule repeating is the enforcer's job (warning scores), not a
    campaign — the burst rule needs breadth, not just count."""
    recent = [_incident(rule_id="r1") for _ in range(20)]
    assert Rulebook().serious_verdict(_finding(), recent).flagged is False


def test_rulebook_thresholds_come_from_root_only_config():
    cfg = config.OverseerConfig(slow_burn_count=3)
    verdict = Rulebook(cfg).checkin_verdict([], [_incident()] * 3)
    assert verdict.flagged is True


# ── the Overseer wiring (rules first, AI as bounded second opinion) ────────

def test_default_overseer_has_no_ai_brain(tmp_path):
    """The default posture is pure rules — no AI consult exists unless root
    config opts in (daemon passes a brain only on overseer.ai_enabled)."""
    o = _overseer(tmp_path)
    assert o.brain is None
    assert o.check_in(now=100) == []
    assert o.on_serious_finding(_finding(), now=100) == []


def test_checkin_produces_finding_from_the_rulebook_alone(tmp_path):
    o = _overseer(tmp_path)
    o.triage.append(_report(sift=[_sift(), _sift()]))
    [finding] = o.check_in(now=100)
    assert finding.track is Track.LEGAL_ETHICAL
    assert finding.severity is Severity.ELEVATED
    assert finding.rule_id == "overseer-checkin"
    assert finding.event.source is Source.OVERSEER


def test_brain_is_not_consulted_when_the_rulebook_flags(tmp_path):
    """AI never vetoes (or even sees) a rules verdict."""
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "would demur"))
    o = _overseer(tmp_path, brain=brain)
    o.triage.append(_report(sift=[_sift(), _sift()]))
    [finding] = o.check_in(now=100)
    assert finding.severity is Severity.ELEVATED
    assert brain.contexts_seen == []


def test_brain_second_opinion_only_on_noteworthy_quiet_periods(tmp_path):
    """The opt-in brain is consulted only when the rulebook found nothing AND
    a report was noteworthy; an unremarkable period costs zero AI calls."""
    brain = _StubBrain(ai.OverseerVerdict(True, Track.LEGAL_ETHICAL,
                                          Severity.ELEVATED, "why"))
    o = _overseer(tmp_path, brain=brain)
    o.triage.append(_report(counts={"security/minor": 1}))   # not noteworthy
    assert o.check_in(now=100) == []
    assert brain.contexts_seen == []
    o.triage.append(_report(ts=150, max_severity="elevated"))  # noteworthy
    [finding] = o.check_in(now=200)
    assert finding.severity is Severity.ELEVATED
    assert len(brain.contexts_seen) == 1


def test_incomplete_brain_verdict_produces_no_finding(tmp_path):
    """flagged=True but no track/severity: fail closed, not a guess."""
    brain = _StubBrain(ai.OverseerVerdict(True, None, None, "vague"))
    o = _overseer(tmp_path, brain=brain)
    o.triage.append(_report(max_severity="elevated"))
    assert o.check_in(now=100) == []


def test_serious_trigger_consults_brain_only_when_rules_stay_quiet(tmp_path):
    brain = _StubBrain(ai.OverseerVerdict(True, Track.SECURITY,
                                          Severity.SERIOUS, "escalate"))
    o = _overseer(tmp_path, brain=brain)
    [finding] = o.on_serious_finding(_finding(), now=100)
    assert finding.rule_id == "overseer-serious-trigger"
    assert finding.severity is Severity.SERIOUS
    [context] = brain.contexts_seen
    assert "SERIOUS finding triggered" in context
    assert "security" in context


def test_serious_trigger_burst_verdict_needs_no_brain(tmp_path):
    o = _overseer(tmp_path)
    for i in range(10):
        o.incidents.record(_finding(sev=Severity.MINOR, rule_id=f"r{i % 4}"),
                           "warn", "", now=90)
    [finding] = o.on_serious_finding(_finding(), now=100)
    assert finding.severity is Severity.SERIOUS
    assert "rulebook/burst" in finding.description


def test_checkin_counts_the_whole_window_from_incidents_db(tmp_path):
    """Slow burn is counted from raw incidents.db entries for the period, not
    just the digests — and produces a Finding end to end."""
    o = _overseer(tmp_path)
    for i in range(12):
        o.incidents.record(_finding(sev=Severity.MINOR, rule_id=f"r{i}"),
                           "warn", "", now=10 + i)
    [finding] = o.check_in(now=100)
    assert finding.track is Track.SECURITY
    assert finding.severity is Severity.ELEVATED
    assert "rulebook/slow-burn" in finding.description


def test_verdict_log_records_every_checkin_including_non_flags(tmp_path):
    path = tmp_path / "verdicts.jsonl"
    o = _overseer(tmp_path)
    o.verdicts = VerdictLog(path)
    o.check_in(now=100)
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["flagged"] is False
    assert entry["trigger"] == "checkin"
    assert entry["engine"] == "rules"


def test_verdict_log_attributes_second_opinions_to_the_ai_engine(tmp_path):
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "quiet"))
    o = _overseer(tmp_path, brain=brain)
    o.triage.append(_report(max_severity="elevated"))
    o.check_in(now=100)
    entry = json.loads((o.verdicts.path).read_text().splitlines()[-1])
    assert entry["engine"] == "ai"


def test_overseer_finding_flows_through_enforcer_like_any_other(tmp_path):
    """No parallel enforcement path: the resulting Finding obeys the exact
    same Enforcer invariants (hard ceiling, scope-by-severity) as a
    rule-engine Finding — regardless of which engine produced the verdict."""
    o = _overseer(tmp_path)
    o.triage.append(_report(ts=1, sift=[_sift()] * 5))
    [finding] = o.check_in(now=1)
    enforcer = Enforcer()
    reaction = enforcer.process(finding, now=1)
    assert reaction.kind is ReactionKind.LOCKOUT
    from frankd.enforcement import Scope
    assert reaction.scope is Scope.MACHINE
    assert enforcer.remaining(1) <= enforcer.cfg.hard_ceiling_seconds
