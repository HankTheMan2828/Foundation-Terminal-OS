"""Sorting/sifting Frank — the middle tier between the rule engine and the
Overseer (this session's addition; see docs/ARCHITECTURE.md).

Runs on its own short interval (config.TriageConfig.interval_seconds — much
more often than the Overseer's check-in, much less often than the rule
engine's per-tick classification). Each run:

  1. Pulls incidents.db entries since the last run and reduces them to
     counts/rule-hit stats — no AI, no judgment call, just arithmetic.
  2. Pulls the raw event log (eventlog.py) since the last run, restricted to
     content-bearing sources, and hands the text to a Sifter (ai.py) for the
     one category the rule engine deliberately left to periodic review
     (docs/OPEN-QUESTIONS.md §3 — hate-speech/extremism).
  3. Writes a `TriageReport` — organized material, not a verdict — for the
     Overseer to read at its own cadence.

Sorting Frank NEVER enforces anything and never decides a violation. It is
pure organize-and-summarize, same spirit as the rule engine/AI-commentary
split: "the rule layer decides what is flagged... the AI ... does not decide."
Here the AI's job is narrower still — classify raw text into the one parked
category, nothing more. The Overseer is the only tier that decides.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import ai
from .eventlog import EventLog
from .incidents import IncidentStore

# Sources worth a content-classification pass. Deliberately excludes
# `process`/`network` — those are numeric/destination signals with nothing
# for a text classifier to read, and including them would be pure volume.
# `activity` is the Hub's per-action feed (note/file/chat text) — the main
# content stream on this OS, so the periodic sift reads it too.
_CONTENT_SOURCES = {"shell", "browser", "activity"}


@dataclass
class TriageReport:
    ts: float
    window_start: float
    window_end: float
    incident_counts: dict[str, int] = field(default_factory=dict)  # "track/severity" -> n
    rule_hits: dict[str, int] = field(default_factory=dict)        # rule_id -> n
    max_severity: str | None = None
    sift_findings: list[ai.SiftFinding] = field(default_factory=list)

    def noteworthy(self) -> bool:
        """Whether this report is worth the Overseer pulling the raw window
        itself, rather than just reading the digest. Deliberately generous —
        false positives here just cost the Overseer one extra read, not an
        enforcement action (only the Overseer's own verdict can do that)."""
        if self.sift_findings:
            return True
        if self.max_severity in ("elevated", "serious"):
            return True
        return sum(self.incident_counts.values()) >= 5

    def summary_text(self) -> str:
        """The non-revealing digest handed to the Overseer's prompt — counts
        and category names, not raw incident content. Sift-finding excerpts
        ARE included: they're the one thing a stats digest can't summarize,
        and the Overseer (unlike mistral.py's Commentator) is meant to see
        enough to actually judge with."""
        lines = [
            f"window: {self.window_start:.0f}..{self.window_end:.0f}",
            f"max_severity: {self.max_severity or 'none'}",
        ]
        if self.incident_counts:
            lines.append("incident_counts: " + ", ".join(
                f"{k}={v}" for k, v in sorted(self.incident_counts.items())))
        if self.rule_hits:
            lines.append("rule_hits: " + ", ".join(
                f"{k}={v}" for k, v in sorted(self.rule_hits.items())))
        if self.sift_findings:
            lines.append("sift_findings:")
            for f_ in self.sift_findings:
                lines.append(f"  - [{f_.category} conf={f_.confidence:.2f}] "
                             f"\"{f_.excerpt}\" — {f_.reasoning}")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "ts": self.ts,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "incident_counts": self.incident_counts,
            "rule_hits": self.rule_hits,
            "max_severity": self.max_severity,
            "sift_findings": [
                {"category": f_.category, "confidence": f_.confidence,
                 "excerpt": f_.excerpt, "reasoning": f_.reasoning}
                for f_ in self.sift_findings
            ],
        }

    @classmethod
    def from_json(cls, d: dict) -> "TriageReport":
        return cls(
            ts=d["ts"], window_start=d["window_start"], window_end=d["window_end"],
            incident_counts=d.get("incident_counts", {}),
            rule_hits=d.get("rule_hits", {}),
            max_severity=d.get("max_severity"),
            sift_findings=[ai.SiftFinding(**f_) for f_ in d.get("sift_findings", [])],
        )


class TriageStore:
    """Frank-only. Same isolation model as incidents.db (0600, never
    surfaced to any user interface)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def append(self, report: TriageReport) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps(report.to_json()) + "\n")

    def since(self, ts: float) -> list[TriageReport]:
        out = []
        try:
            with self.path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    if d.get("ts", 0) > ts:
                        out.append(TriageReport.from_json(d))
        except OSError:
            pass
        return out

    def latest(self) -> TriageReport | None:
        reports = self.since(0)
        return reports[-1] if reports else None


_SEVERITY_ORDER = ["observe", "minor", "elevated", "serious"]


def _max_severity(severities: list[str]) -> str | None:
    ranked = [s for s in severities if s in _SEVERITY_ORDER]
    if not ranked:
        return None
    return max(ranked, key=_SEVERITY_ORDER.index)


class TriageEngine:
    def __init__(self, incidents: IncidentStore, eventlog: EventLog,
                 store: TriageStore, sifter: ai.Sifter | None = None,
                 last_run: float | None = None):
        self.incidents = incidents
        self.eventlog = eventlog
        self.store = store
        self.sifter = sifter or ai.build_sifter()
        # Resume from the last report's window end, if any, so a daemon
        # restart doesn't re-scan (or skip) the gap.
        if last_run is not None:
            self._last_run = last_run
        else:
            latest = store.latest()
            self._last_run = latest.window_end if latest else 0.0

    def run(self, now: float) -> TriageReport:
        start, end = self._last_run, now
        incidents = self.incidents.between(start, end)
        events = self.eventlog.between(start, end)

        counts: dict[str, int] = {}
        rule_hits: dict[str, int] = {}
        severities: list[str] = []
        for entry in incidents:
            key = f"{entry.get('track')}/{entry.get('severity', '').lower()}"
            counts[key] = counts.get(key, 0) + 1
            rid = entry.get("rule_id", "?")
            rule_hits[rid] = rule_hits.get(rid, 0) + 1
            severities.append(entry.get("severity", "").lower())

        texts = [e["text"] for e in events if e.get("source") in _CONTENT_SOURCES]
        sift_findings = self.sifter.analyze(texts)

        report = TriageReport(
            ts=now, window_start=start, window_end=end,
            incident_counts=counts, rule_hits=rule_hits,
            max_severity=_max_severity(severities), sift_findings=sift_findings,
        )
        self.store.append(report)
        self._last_run = now
        return report
