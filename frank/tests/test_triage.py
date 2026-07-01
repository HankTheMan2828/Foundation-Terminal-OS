"""Sorting/sifting Frank (spec: organizes recent activity for the Overseer;
never enforces, never decides a violation itself)."""
from frankd import ai
from frankd.enforcement import Enforcer
from frankd.eventlog import EventLog
from frankd.model import Event, Finding, Severity, Source, Track
from frankd.triage import TriageEngine, TriageReport, TriageStore


def _finding(track, sev, rule_id="r1"):
    return Finding(rule_id, track, sev, Event(Source.SHELL, "x"), matched="x")


class _StubSifter:
    def __init__(self, findings=None):
        self._findings = findings or []

    def analyze(self, texts):
        return list(self._findings)


def _engine(tmp_path, incidents=None, eventlog=None, sifter=None):
    from frankd.incidents import IncidentStore
    incidents = incidents or IncidentStore(tmp_path / "incidents.db")
    eventlog = eventlog or EventLog(tmp_path / "events.log")
    store = TriageStore(tmp_path / "triage.jsonl")
    return TriageEngine(incidents, eventlog, store, sifter=sifter or _StubSifter())


def test_run_produces_no_findings_object_only_a_report(tmp_path):
    """Triage NEVER produces an enforceable Finding -- only a TriageReport."""
    engine = _engine(tmp_path)
    report = engine.run(now=100)
    assert isinstance(report, TriageReport)


def test_incident_counts_grouped_by_track_and_severity(tmp_path):
    from frankd.incidents import IncidentStore
    incidents = IncidentStore(tmp_path / "incidents.db")
    e = Enforcer()
    incidents.record(_finding(Track.SECURITY, Severity.MINOR), "warn", "", now=10)
    incidents.record(_finding(Track.SECURITY, Severity.MINOR), "warn", "", now=20)
    incidents.record(_finding(Track.LEGAL_ETHICAL, Severity.SERIOUS), "lockout", "", now=30)
    engine = _engine(tmp_path, incidents=incidents)
    report = engine.run(now=1000)
    assert report.incident_counts["security/minor"] == 2
    assert report.incident_counts["legal_ethical/serious"] == 1
    assert report.max_severity == "serious"


def test_rule_hit_counts_by_rule_id(tmp_path):
    from frankd.incidents import IncidentStore
    incidents = IncidentStore(tmp_path / "incidents.db")
    incidents.record(_finding(Track.SECURITY, Severity.MINOR, "sec-a"), "warn", "", now=10)
    incidents.record(_finding(Track.SECURITY, Severity.MINOR, "sec-a"), "warn", "", now=20)
    incidents.record(_finding(Track.SECURITY, Severity.MINOR, "sec-b"), "warn", "", now=30)
    engine = _engine(tmp_path, incidents=incidents)
    report = engine.run(now=1000)
    assert report.rule_hits == {"sec-a": 2, "sec-b": 1}


def test_only_content_bearing_sources_go_to_the_sifter(tmp_path):
    eventlog = EventLog(tmp_path / "events.log")
    eventlog.record(Event(Source.SHELL, "shell text", ts=1))
    eventlog.record(Event(Source.BROWSER, "browser text", ts=1))
    eventlog.record(Event(Source.PROCESS, "ffmpeg", ts=1))   # not content-bearing
    eventlog.record(Event(Source.NETWORK, "connect 1.2.3.4", ts=1))  # not content-bearing

    seen = []

    class _Recording(_StubSifter):
        def analyze(self, texts):
            seen.extend(texts)
            return []

    engine = _engine(tmp_path, eventlog=eventlog, sifter=_Recording())
    engine.run(now=1000)
    assert set(seen) == {"shell text", "browser text"}


def test_sift_findings_flow_into_the_report(tmp_path):
    finding = ai.SiftFinding("hate_speech_extremism", 0.9, "some line", "reasoning")
    eventlog = EventLog(tmp_path / "events.log")
    eventlog.record(Event(Source.SHELL, "some line", ts=1))
    engine = _engine(tmp_path, eventlog=eventlog, sifter=_StubSifter([finding]))
    report = engine.run(now=1000)
    assert report.sift_findings == [finding]
    assert report.noteworthy()


def test_report_not_noteworthy_when_quiet(tmp_path):
    engine = _engine(tmp_path)
    report = engine.run(now=1000)
    assert not report.noteworthy()


def test_report_noteworthy_on_high_volume_even_without_sift_hits(tmp_path):
    from frankd.incidents import IncidentStore
    incidents = IncidentStore(tmp_path / "incidents.db")
    for i in range(5):
        incidents.record(_finding(Track.SECURITY, Severity.MINOR), "warn", "", now=i)
    engine = _engine(tmp_path, incidents=incidents)
    report = engine.run(now=1000)
    assert report.noteworthy()


def test_run_resumes_from_previous_report_window_end(tmp_path):
    """A fresh TriageEngine built against an existing store picks up where the
    last report left off, so a daemon restart doesn't re-scan or skip time."""
    from frankd.incidents import IncidentStore
    incidents = IncidentStore(tmp_path / "incidents.db")
    eventlog = EventLog(tmp_path / "events.log")
    store = TriageStore(tmp_path / "triage.jsonl")

    engine1 = TriageEngine(incidents, eventlog, store, sifter=_StubSifter())
    engine1.run(now=100)

    engine2 = TriageEngine(incidents, eventlog, store, sifter=_StubSifter())
    assert engine2._last_run == 100
    report2 = engine2.run(now=200)
    assert report2.window_start == 100
    assert report2.window_end == 200


def test_report_round_trips_through_store(tmp_path):
    store = TriageStore(tmp_path / "triage.jsonl")
    finding = ai.SiftFinding("hate_speech_extremism", 0.5, "x", "y")
    report = TriageReport(ts=10, window_start=0, window_end=10,
                           incident_counts={"security/minor": 1},
                           rule_hits={"r1": 1}, max_severity="minor",
                           sift_findings=[finding])
    store.append(report)
    [loaded] = store.since(0)
    assert loaded.incident_counts == report.incident_counts
    assert loaded.sift_findings == [finding]
    assert store.latest().ts == 10
