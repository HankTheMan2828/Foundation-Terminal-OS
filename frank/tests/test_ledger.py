"""Visible ledger invariant (spec §6): TIMESTAMPS ONLY, nothing else."""
import re

from frankd.ledger import TimestampLedger

TS_RE = re.compile(r"^\d{8}T\d{6}Z$")   # compact basic ISO 8601, UTC


def test_ledger_records_only_timestamps(tmp_path):
    led = TimestampLedger(tmp_path / "ledger.timestamps")
    led.record(1_750_000_000.0)
    led.record(1_750_000_060.0)
    lines = led.read()
    assert len(lines) == 2
    # Every line must be a bare machine-formatted timestamp — no category,
    # severity, description, or content may ever appear here (spec §6).
    for line in lines:
        assert TS_RE.match(line), f"non-timestamp content leaked into ledger: {line!r}"


def test_daily_reset_truncates_ledger(tmp_path):
    led = TimestampLedger(tmp_path / "ledger.timestamps")
    led.record(1_750_000_000.0)
    led.reset_daily()
    assert led.read() == []
