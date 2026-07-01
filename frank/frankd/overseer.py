"""Main Frank — the Overseer (this session's addition; see docs/ARCHITECTURE.md).

What the operator described this session: a tier above the rule engine and
sorting/sifting Frank (triage.py) that can "intervene on any and all levels."
Concretely, that means it can produce a `Finding` of any track/severity —
same as the rule engine can — and that Finding runs through the exact same
`Enforcer.process()`. There is no separate enforcement path for the Overseer,
which is what makes "the same hard ceiling applies to the Overseer"
(operator-confirmed this session) true structurally rather than by promise.

Two activation paths (operator-confirmed this session):
  * Periodic check-in — `check_in()`, called by the daemon on
    config.OverseerConfig.checkin_interval_hours (1-2x/day). Reads every
    `TriageReport` accumulated since the last check-in.
  * Immediate trigger — `on_serious_finding()`, called the moment the rule
    engine's Enforcer processes a SERIOUS-severity finding. Lesser
    warnings/lockouts do NOT wake the Overseer early; they wait for the next
    scheduled check-in (operator-confirmed scope: "serious-severity findings
    only" for the immediate path).

When a triage report looks worth a closer look (`TriageReport.noteworthy()`),
the Overseer queries `IncidentStore`/`EventLog` directly for that report's
time window — a plain method call, not a subagent — because one judgment
call doesn't need the isolation or ceremony of spinning up a separate agent,
and skipping that round-trip is the context/cost saving the operator asked
for. Same idea on the immediate path: it pulls its own short lookback window
around the triggering finding.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import ai
from .eventlog import EventLog
from .incidents import IncidentStore
from .model import Event, Finding, Source
from .triage import TriageReport, TriageStore

# How far back the immediate SERIOUS-trigger path looks for context. Kept
# short deliberately — this path answers "is this finding part of something
# bigger happening right now?", not a historical review (that's check_in()'s
# job, via triage's own longer window).
SERIOUS_CONTEXT_WINDOW_SECONDS = 300

# Cap on how many raw incident lines go into one prompt. This is a judgment
# call, not a forensic export — bounding it keeps cost predictable and
# matches the "one review, not a dump" intent.
MAX_CONTEXT_INCIDENTS = 50


class VerdictLog:
    """Frank-only audit trail of every Overseer decision, including the
    "nothing to see here" ones — distinct from incidents.db, which only ever
    records a Finding (i.e. only what the Overseer decided to flag). Useful
    for tuning/debugging the Overseer itself; never surfaced to any user
    interface, same isolation model as incidents.db (0600)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)

    def append(self, now: float, trigger: str, verdict: ai.OverseerVerdict,
               context: str) -> None:
        entry = {
            "ts": now,
            "trigger": trigger,
            "flagged": verdict.flagged,
            "track": verdict.track.value if verdict.track else None,
            "severity": verdict.severity.name if verdict.severity else None,
            "reasoning": verdict.reasoning,
            "context": context,
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")


class Overseer:
    def __init__(self, triage: TriageStore, incidents: IncidentStore,
                 eventlog: EventLog, verdicts: VerdictLog,
                 brain: ai.OverseerBrain | None = None,
                 last_checkin: float | None = None):
        self.triage = triage
        self.incidents = incidents
        self.eventlog = eventlog
        self.verdicts = verdicts
        self.brain = brain or ai.build_overseer_brain()
        self._last_checkin = 0.0 if last_checkin is None else last_checkin

    # ── periodic path ────────────────────────────────────────────────────
    def check_in(self, now: float, activity_snapshot: str = "") -> list[Finding]:
        reports = self.triage.since(self._last_checkin)
        context = self._checkin_context(reports, activity_snapshot)
        verdict = self.brain.decide(context)
        self.verdicts.append(now, "checkin", verdict, context)
        self._last_checkin = now
        return self._to_findings(verdict, "overseer-checkin")

    def _checkin_context(self, reports: list[TriageReport],
                          activity_snapshot: str) -> str:
        lines = ["=== triage reports since last check-in ==="]
        if not reports:
            lines.append("(none)")
        for report in reports:
            lines.append(report.summary_text())
            if report.noteworthy():
                # The "select a time period from the base logs" step: read
                # the raw window itself instead of trusting the digest alone.
                window = self.incidents.between(report.window_start, report.window_end)
                lines.append(f"  raw window ({len(window)} incidents):")
                for entry in window[:MAX_CONTEXT_INCIDENTS]:
                    lines.append(f"    {entry.get('track')}/{entry.get('severity')} "
                                 f"via {entry.get('source')}: {entry.get('matched')}")
        lines.append("=== current activity ===")
        lines.append(activity_snapshot or "(not supplied)")
        return "\n".join(lines)

    # ── immediate trigger path ───────────────────────────────────────────
    def on_serious_finding(self, finding: Finding, now: float) -> list[Finding]:
        recent = self.incidents.between(now - SERIOUS_CONTEXT_WINDOW_SECONDS, now)
        context = self._serious_context(finding, recent)
        verdict = self.brain.decide(context)
        self.verdicts.append(now, "serious_trigger", verdict, context)
        return self._to_findings(verdict, "overseer-serious-trigger")

    def _serious_context(self, finding: Finding, recent: list[dict]) -> str:
        lines = [
            "=== SERIOUS finding triggered immediate review ===",
            f"rule_id={finding.rule_id} track={finding.track.value} "
            f"source={finding.event.source.value}: {finding.matched}",
            f"=== last {SERIOUS_CONTEXT_WINDOW_SECONDS}s of incidents "
            f"({len(recent)}) ===",
        ]
        for entry in recent[:MAX_CONTEXT_INCIDENTS]:
            lines.append(f"  {entry.get('track')}/{entry.get('severity')} "
                         f"via {entry.get('source')}: {entry.get('matched')}")
        return "\n".join(lines)

    # ── shared ───────────────────────────────────────────────────────────
    def _to_findings(self, verdict: ai.OverseerVerdict, rule_id: str) -> list[Finding]:
        if not verdict.flagged or verdict.track is None or verdict.severity is None:
            return []
        event = Event(Source.OVERSEER, "overseer judgment call")
        return [Finding(
            rule_id=rule_id,
            track=verdict.track,
            severity=verdict.severity,
            event=event,
            matched="(no single matched string — overseer judgment)",
            description=verdict.reasoning,
        )]
