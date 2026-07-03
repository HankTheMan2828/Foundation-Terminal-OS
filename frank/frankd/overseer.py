"""Main Frank — the Overseer (see docs/ARCHITECTURE.md).

Operator direction: Frank is a **primarily rule-based overseer system**
(OPEN-QUESTIONS.md §5) — the AI layer stays secondary. Verdicts come from
`Rulebook` — deterministic thresholds over the structured material the lower
tiers already produce (triage digests, incident windows) — so the tier works
identically on every machine, online or off. The AI brain (`ai.OverseerBrain`)
is demoted to an optional second opinion:

  * OFF by default (`config.OverseerConfig.ai_enabled`), requires a key too;
  * consulted only when the rulebook flagged NOTHING and the period still
    looks noteworthy — never to second-guess a verdict the rulebook reached;
  * its verdict is bounded exactly like the rulebook's (below).

What survives unchanged from the original design: the Overseer sits above
the rule engine and sorting/sifting tier (triage.py) and can "intervene on
any and all levels" — it can produce a `Finding` of any track/severity, and
that Finding runs through the exact same `Enforcer.process()` (routed by
`UserEnforcers` per the multi-user model). There is no separate enforcement
path for the Overseer, which is what makes "the same hard ceiling applies to
the Overseer" (operator-confirmed) true structurally rather than by promise.

Two activation paths (operator-confirmed):
  * Periodic check-in — `check_in()`, called by the daemon on
    config.OverseerConfig.checkin_interval_seconds (1-2x/day). Reads every
    `TriageReport` accumulated since the last check-in, plus the raw
    incident window for the whole period (the rulebook counts real entries,
    not just digests).
  * Immediate trigger — `on_serious_finding()`, called the moment the rule
    engine's Enforcer processes a SERIOUS-severity finding. Lesser
    warnings/lockouts do NOT wake the Overseer early; they wait for the next
    scheduled check-in (operator-confirmed scope).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ai, config
from .eventlog import EventLog
from .incidents import IncidentStore
from .model import Event, Finding, Severity, Source, Track
from .triage import TriageReport, TriageStore

# How far back the immediate SERIOUS-trigger path looks for context. Kept
# short deliberately — this path answers "is this finding part of something
# bigger happening right now?", not a historical review (that's check_in()'s
# job, via triage's own longer window).
SERIOUS_CONTEXT_WINDOW_SECONDS = 300

# Cap on how many raw incident lines go into one AI prompt (second-opinion
# path only). This is a judgment call, not a forensic export — bounding it
# keeps cost predictable and matches the "one review, not a dump" intent.
MAX_CONTEXT_INCIDENTS = 50

# Findings the Overseer itself produced, as recorded in incidents.db. The
# rulebook must never count these — an Overseer verdict feeding the next
# Overseer verdict would be a feedback loop.
_OVERSEER_RULE_PREFIX = "overseer-"

_TRACKS = {t.value: t for t in Track}


class Rulebook:
    """The Overseer's deterministic brain. Pure arithmetic over structured
    data — no model, no network, no nondeterminism — so every verdict is
    reproducible from the logs and works on an offline machine.

    Each rule covers a pattern the realtime rule engine deliberately cannot
    see (its horizon is one event; the enforcer's warning score decays after
    5 quiet minutes):

      * sift accumulation — ai.Sifter classifications of the one parked
        content category (docs/OPEN-QUESTIONS.md §3) are treated as SENSOR
        readings, not verdicts: the decision is this threshold, applied to
        confident readings accumulated across the whole check-in period.
      * slow burn — many enforced incidents on one track scattered across
        the period, each too far apart to stack a warning score.
      * burst (SERIOUS-trigger path) — a serious finding arriving in the
        middle of a wide spray of other incidents is treated as part of a
        campaign, not an isolated event.
    """

    def __init__(self, cfg: config.OverseerConfig | None = None):
        self.cfg = cfg or config.OverseerConfig()

    # ── check-in rules ───────────────────────────────────────────────────
    def checkin_verdict(self, reports: list[TriageReport],
                        incidents: list[dict]) -> ai.OverseerVerdict:
        candidates = []
        sift = self._sift_rule(reports)
        if sift:
            candidates.append(sift)
        burn = self._slow_burn_rule(incidents)
        if burn:
            candidates.append(burn)
        if not candidates:
            return ai.OverseerVerdict(False, None, None,
                                      "rulebook: no threshold crossed")
        return max(candidates, key=lambda v: v.severity)

    def _sift_rule(self, reports: list[TriageReport]) -> ai.OverseerVerdict | None:
        confident = [f for r in reports for f in r.sift_findings
                     if f.confidence >= self.cfg.sift_confidence_threshold]
        n = len(confident)
        if n == 0:
            return None
        if n >= self.cfg.sift_serious_count:
            severity = Severity.SERIOUS
        elif n >= self.cfg.sift_elevated_count:
            severity = Severity.ELEVATED
        else:
            severity = Severity.MINOR
        cats = sorted({f.category for f in confident})
        return ai.OverseerVerdict(
            True, Track.LEGAL_ETHICAL, severity,
            f"rulebook/sift: {n} confident sift finding(s) "
            f"(>= {self.cfg.sift_confidence_threshold:.2f}) in {cats} "
            f"since last check-in")

    def _slow_burn_rule(self, incidents: list[dict]) -> ai.OverseerVerdict | None:
        counts: dict[str, int] = {}
        for entry in incidents:
            if str(entry.get("rule_id", "")).startswith(_OVERSEER_RULE_PREFIX):
                continue   # never count our own prior verdicts
            if str(entry.get("severity", "")).upper() == Severity.OBSERVE.name:
                continue   # observe-tier stays outside the punitive pipeline
            track = entry.get("track", "")
            counts[track] = counts.get(track, 0) + 1
        worst = max(counts, key=counts.get, default=None)
        if worst is None or counts[worst] < self.cfg.slow_burn_count or worst not in _TRACKS:
            return None
        return ai.OverseerVerdict(
            True, _TRACKS[worst], Severity.ELEVATED,
            f"rulebook/slow-burn: {counts[worst]} enforced incidents on the "
            f"{worst} track across one check-in period "
            f"(threshold {self.cfg.slow_burn_count})")

    # ── SERIOUS-trigger rule ─────────────────────────────────────────────
    def serious_verdict(self, finding: Finding,
                        recent: list[dict]) -> ai.OverseerVerdict:
        others = [e for e in recent
                  if not str(e.get("rule_id", "")).startswith(_OVERSEER_RULE_PREFIX)]
        distinct = {e.get("rule_id") for e in others}
        if (len(others) >= self.cfg.burst_incident_count
                and len(distinct) >= self.cfg.burst_distinct_rules):
            return ai.OverseerVerdict(
                True, finding.track, Severity.SERIOUS,
                f"rulebook/burst: serious finding {finding.rule_id} arrived "
                f"amid {len(others)} incidents across {len(distinct)} rules "
                f"in the last {SERIOUS_CONTEXT_WINDOW_SECONDS}s")
        return ai.OverseerVerdict(False, None, None,
                                  "rulebook: serious finding stands alone; "
                                  "enforcer already handled it")


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
               context: str, engine: str = "rules") -> None:
        entry = {
            "ts": now,
            "trigger": trigger,
            "engine": engine,   # "rules" (the norm) or "ai" (second opinion)
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
                 rulebook: Rulebook | None = None,
                 brain: ai.OverseerBrain | None = None,
                 last_checkin: float | None = None):
        self.triage = triage
        self.incidents = incidents
        self.eventlog = eventlog
        self.verdicts = verdicts
        self.rulebook = rulebook or Rulebook()
        # brain=None is the DEFAULT posture: no AI consult at all. The daemon
        # only passes one when root config sets overseer.ai_enabled AND a key
        # exists — and even then it is a second opinion, never a veto.
        self.brain = brain
        self._last_checkin = 0.0 if last_checkin is None else last_checkin

    # ── periodic path ────────────────────────────────────────────────────
    def check_in(self, now: float, activity_snapshot: str = "") -> list[Finding]:
        reports = self.triage.since(self._last_checkin)
        window = self.incidents.between(self._last_checkin, now)
        context = self._checkin_context(reports, activity_snapshot)
        verdict = self.rulebook.checkin_verdict(reports, window)
        engine = "rules"
        if (not verdict.flagged and self.brain is not None
                and any(r.noteworthy() for r in reports)):
            verdict, engine = self.brain.decide(context), "ai"
        self.verdicts.append(now, "checkin", verdict, context, engine)
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
        verdict = self.rulebook.serious_verdict(finding, recent)
        engine = "rules"
        if not verdict.flagged and self.brain is not None:
            verdict, engine = self.brain.decide(context), "ai"
        self.verdicts.append(now, "serious_trigger", verdict, context, engine)
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
