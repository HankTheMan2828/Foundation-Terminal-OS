"""The raw base-log store triage.py/overseer.py sift (this session)."""
from frankd.eventlog import EventLog
from frankd.model import Event, Source


def _log(tmp_path):
    return EventLog(tmp_path / "events.log", retention_seconds=100)


def test_record_and_query_by_time_window(tmp_path):
    log = _log(tmp_path)
    log.record(Event(Source.SHELL, "ls -la", ts=10))
    log.record(Event(Source.SHELL, "curl evil.example", ts=20))
    log.record(Event(Source.BROWSER, "some search", ts=30))

    window = log.between(15, 25)
    assert [e["text"] for e in window] == ["curl evil.example"]


def test_since_is_between_with_open_end(tmp_path):
    log = _log(tmp_path)
    log.record(Event(Source.SHELL, "a", ts=1))
    log.record(Event(Source.SHELL, "b", ts=1000))
    assert [e["text"] for e in log.since(500)] == ["b"]


def test_prune_drops_entries_older_than_retention(tmp_path):
    log = _log(tmp_path)
    log.record(Event(Source.SHELL, "old", ts=-5))   # older than cutoff (0)
    log.record(Event(Source.SHELL, "new", ts=90))
    log.prune(now=100)  # retention_seconds=100 -> cutoff=0
    remaining = [e["text"] for e in log.since(-100)]
    assert "new" in remaining
    assert "old" not in remaining


def test_prune_keeps_everything_within_window(tmp_path):
    log = _log(tmp_path)
    log.record(Event(Source.SHELL, "a", ts=50))
    log.record(Event(Source.SHELL, "b", ts=60))
    log.prune(now=100)  # cutoff=0, nothing dropped
    assert len(log.since(-1)) == 2
