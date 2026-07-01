"""Main Frank / the Overseer (spec: intervenes via the SAME Enforcer path as
the rule engine -- no separate/parallel enforcement channel)."""
import json

from frankd import ai
from frankd.enforcement import Enforcer, ReactionKind
from frankd.eventlog import EventLog
from frankd.incidents import IncidentStore
from frankd.model import Event, Finding, Severity, Source, Track
from frankd.overseer import Overseer, VerdictLog
from frankd.triage import TriageReport, TriageStore


def _finding(track=Track.SECURITY, sev=Severity.SERIOUS, source=Source.SHELL):
    return Finding("r", track, sev, Event(source, "x"), matched="x")


class _StubBrain:
    def __init__(self, verdict):
        self.verdict = verdict
        self.contexts_seen = []

    def decide(self, context):
        self.contexts_seen.append(context)
        return self.verdict


def _overseer(tmp_path, brain):
    triage = TriageStore(tmp_path / "triage.jsonl")
    incidents = IncidentStore(tmp_path / "incidents.db")
    eventlog = EventLog(tmp_path / "events.log")
    verdicts = VerdictLog(tmp_path / "verdicts.jsonl")
    return Overseer(triage, incidents, eventlog, verdicts, brain=brain)


def test_offline_default_never_flags(tmp_path):
    """With no key configured (the test environment), build_overseer_brain()
    resolves to OfflineOverseer -- the safe default (spec: an unattended
    heuristic escalating on its own is a worse failure than under-triggering)."""
    o = _overseer(tmp_path, brain=ai.build_overseer_brain())
    assert o.check_in(now=100) == []
    assert o.on_serious_finding(_finding(), now=100) == []


def test_checkin_produces_finding_when_brain_flags(tmp_path):
    verdict = ai.OverseerVerdict(True, Track.LEGAL_ETHICAL, Severity.ELEVATED, "why")
    o = _overseer(tmp_path, brain=_StubBrain(verdict))
    [finding] = o.check_in(now=100)
    assert finding.track is Track.LEGAL_ETHICAL
    assert finding.severity is Severity.ELEVATED
    assert finding.rule_id == "overseer-checkin"
    assert finding.event.source is Source.OVERSEER


def test_incomplete_verdict_produces_no_finding(tmp_path):
    """flagged=True but no track/severity: fail closed, not a guess."""
    verdict = ai.OverseerVerdict(True, None, None, "vague")
    o = _overseer(tmp_path, brain=_StubBrain(verdict))
    assert o.check_in(now=100) == []


def test_serious_trigger_produces_finding_with_its_own_rule_id(tmp_path):
    verdict = ai.OverseerVerdict(True, Track.SECURITY, Severity.SERIOUS, "escalate")
    o = _overseer(tmp_path, brain=_StubBrain(verdict))
    [finding] = o.on_serious_finding(_finding(), now=100)
    assert finding.rule_id == "overseer-serious-trigger"
    assert finding.severity is Severity.SERIOUS


def test_serious_trigger_context_includes_the_triggering_finding(tmp_path):
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "nothing"))
    o = _overseer(tmp_path, brain=brain)
    finding = _finding(track=Track.SECURITY)
    o.on_serious_finding(finding, now=100)
    [context] = brain.contexts_seen
    assert "SERIOUS finding triggered" in context
    assert "security" in context


def test_checkin_reads_triage_reports_since_last_checkin(tmp_path):
    triage = TriageStore(tmp_path / "triage.jsonl")
    triage.append(TriageReport(ts=50, window_start=0, window_end=50,
                                incident_counts={"security/minor": 1}))
    incidents = IncidentStore(tmp_path / "incidents.db")
    eventlog = EventLog(tmp_path / "events.log")
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "nothing"))
    o = Overseer(triage, incidents, eventlog, VerdictLog(tmp_path / "verdicts.jsonl"),
                 brain=brain)
    o.check_in(now=100)
    [context] = brain.contexts_seen
    assert "security/minor" in context


def test_checkin_pulls_raw_window_for_noteworthy_reports(tmp_path):
    """The "select a time period from the base logs to sift through" step:
    a noteworthy report makes the Overseer read the raw incidents itself,
    not just the digest."""
    triage = TriageStore(tmp_path / "triage.jsonl")
    incidents = IncidentStore(tmp_path / "incidents.db")
    incidents.record(_finding(sev=Severity.SERIOUS), "lockout", "", now=10)
    triage.append(TriageReport(ts=50, window_start=0, window_end=50,
                                max_severity="serious"))  # noteworthy: serious
    eventlog = EventLog(tmp_path / "events.log")
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "nothing"))
    o = Overseer(triage, incidents, eventlog, VerdictLog(tmp_path / "verdicts.jsonl"),
                 brain=brain)
    o.check_in(now=100)
    [context] = brain.contexts_seen
    assert "raw window" in context
    assert "security/SERIOUS" in context


def test_checkin_includes_the_activity_snapshot(tmp_path):
    brain = _StubBrain(ai.OverseerVerdict(False, None, None, "nothing"))
    o = _overseer(tmp_path, brain=brain)
    o.check_in(now=100, activity_snapshot="operator is compiling a kernel")
    [context] = brain.contexts_seen
    assert "operator is compiling a kernel" in context


def test_verdict_log_records_every_checkin_including_non_flags(tmp_path):
    path = tmp_path / "verdicts.jsonl"
    o = _overseer(tmp_path, brain=_StubBrain(ai.OverseerVerdict(False, None, None, "quiet")))
    o.verdicts = VerdictLog(path)
    o.check_in(now=100)
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["flagged"] is False
    assert entry["trigger"] == "checkin"


def test_overseer_finding_flows_through_enforcer_like_any_other(tmp_path):
    """No parallel enforcement path: the resulting Finding obeys the exact
    same Enforcer invariants (hard ceiling, scope-by-severity) as a
    rule-engine Finding."""
    verdict = ai.OverseerVerdict(True, Track.SECURITY, Severity.SERIOUS, "escalate")
    o = _overseer(tmp_path, brain=_StubBrain(verdict))
    [finding] = o.check_in(now=0)
    enforcer = Enforcer()
    reaction = enforcer.process(finding, now=0)
    assert reaction.kind is ReactionKind.LOCKOUT
    from frankd.enforcement import Scope
    assert reaction.scope is Scope.MACHINE
    assert enforcer.remaining(0) <= enforcer.cfg.hard_ceiling_seconds
