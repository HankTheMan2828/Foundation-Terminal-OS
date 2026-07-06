"""Frank's configuration + the sensitivity model (spec §6).

Config lives at /etc/frank/ (root:frank, unreadable by the operator). NOTHING
here is operator-tunable. Sensitivity (1–5) is a ROOT-ONLY value loaded once at
startup; there is no in-session path — no IPC command, no Settings screen, no
editable file — by which the operator can change it or anything else about
Frank. The operator has no power over Frank, ever. (This tightens the spec §5
mention of exposed sensitivity tuning, at the user's explicit direction.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .model import Severity

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

CONFIG_DIR = Path("/etc/frank")
DEFAULT_CONFIG = CONFIG_DIR / "config.toml"
RULES_DIR = CONFIG_DIR / "rules.d"


@dataclass
class EnforcementConfig:
    """Tunables for the warning/lockout state machine. See enforcement.py."""
    # Cumulative escalation weight per severity. Higher weight => "fewer warnings
    # before action" (spec §6: serious skips straight to fewer warnings).
    # OBSERVE is listed for completeness but Enforcer.process() bypasses the
    # weight/threshold math for it entirely — it never warns or locks out.
    weights: dict[Severity, int] = field(default_factory=lambda: {
        Severity.OBSERVE: 0,
        Severity.MINOR: 1,
        Severity.ELEVATED: 2,
        Severity.SERIOUS: 4,
    })
    # Cross the threshold => lockout. With threshold 4 and the weights above:
    # minor -> 3 warnings then lock on the 4th; elevated -> 1 warning then lock
    # on the 2nd; serious -> immediate (operator-confirmed: "3 warnings total").
    warning_threshold: int = 4
    # If a track has gone quiet for longer than this, its accrued warning score
    # decays back to zero on the next finding instead of continuing to stack —
    # a burst of minor flags should count against you, but scattered one-offs
    # weeks apart shouldn't slowly build toward a lockout (operator-confirmed).
    track_score_decay_seconds: int = 300   # 5 minutes
    # Base lockout seconds by the severity that triggered it (spec §6:
    # severity -> duration). Minor/elevated lock the session; serious the
    # machine. Halved from the original first draft per operator direction.
    base_lockout_seconds: dict[Severity, int] = field(default_factory=lambda: {
        Severity.MINOR: 150,      # 2.5 min, session/console only
        Severity.ELEVATED: 450,   # 7.5 min, session/console only
        Severity.SERIOUS: 900,    # 15 min, whole machine
    })
    # The absolute ceiling on ANY lockout (spec §6). Frank can extend up to this
    # for severe violations but can NEVER exceed it; it always eventually expires.
    hard_ceiling_seconds: int = 1800  # 30 min, hard.
    # How much a further severe finding extends an ACTIVE lockout (clamped to
    # ceiling-from-start).
    extension_seconds: int = 300


@dataclass
class TriageConfig:
    """Sorting/sifting Frank (frankd/triage.py) — the middle tier. Runs far
    more often than the Overseer, on plain arithmetic + one cheap content
    scan; see docs/OPEN-QUESTIONS.md for model-tier recommendations."""
    interval_seconds: int = 900        # 15 min


@dataclass
class OverseerConfig:
    """Main Frank / the Overseer (frankd/overseer.py) — operator-confirmed:
    periodic check-in 1-2x/day, PLUS an immediate wake on any SERIOUS-severity
    finding (not on lesser lockouts/warnings).

    Operator direction: Frank is a primarily rule-based overseer system —
    the AI layer stays secondary (OPEN-QUESTIONS.md §5). Verdicts come from
    the deterministic thresholds below (overseer.Rulebook), which run
    identically online or offline. The AI brain is an optional second
    opinion, OFF by default, consulted only when the rulebook found nothing
    and the period still looks noteworthy — and it can only add a verdict,
    never veto one."""
    checkin_interval_seconds: int = 12 * 3600   # twice a day
    wake_on_serious: bool = True
    # ── deterministic rulebook thresholds (all root-only, like sensitivity) ──
    # Sift findings (ai.Sifter's classifications of the one parked content
    # category) below this confidence are ignored entirely.
    sift_confidence_threshold: float = 0.75
    # Confident sift findings accumulated across a check-in period:
    # 1..elevated_count-1 -> MINOR, >=elevated_count -> ELEVATED,
    # >=serious_count -> SERIOUS (all on the legal_ethical track).
    sift_elevated_count: int = 2
    sift_serious_count: int = 5
    # Slow-burn: this many enforced (non-OBSERVE) incidents on one track
    # across a whole check-in period -> ELEVATED, catching scatter that the
    # enforcer's 5-minute warning-score decay deliberately lets slide.
    slow_burn_count: int = 12
    # Burst rule for the immediate SERIOUS-trigger path: at least this many
    # incidents, across at least this many distinct rules, in the short
    # lookback window around the trigger -> SERIOUS (extends the lockout
    # through the same Enforcer, still under the same hard ceiling).
    burst_incident_count: int = 10
    burst_distinct_rules: int = 3
    # Optional AI second opinion. Requires a key AND this flag; default off.
    ai_enabled: bool = False


@dataclass
class SiftConfig:
    """The content sensor's backend (frankd/ai.py). Operator direction
    (2026-07-06): a lightweight LOCAL model (IBM Granite Guardian) so Frank's
    AI layer needs no cloud key and no network — see docs/FRANK-AI-GUARDIAN.md.

    backend:
      "offline" — no model; the sensor reads nothing (rules/stats still run).
      "local"   — a local OpenAI-compatible Guardian endpoint (llama.cpp/vLLM)
                  on 127.0.0.1. The default once weights are installed.
      "cloud"   — the original Mistral ChatSifter (needs a key).

    Everything else about the pipeline is unchanged: the sifter is a SENSOR;
    its readings become findings only through the Overseer's Rulebook."""
    backend: str = "offline"
    base_url: str = "http://127.0.0.1:8080/v1/chat/completions"
    model: str = "granite-guardian"
    # A Guardian "risk = yes" below this probability is ignored as noise. The
    # Overseer's own sift_confidence_threshold then applies a SECOND gate before
    # anything accumulates toward a verdict — deliberately two independent gates.
    confidence_threshold: float = 0.6


@dataclass
class NegotiationConfig:
    """Negotiable lockouts (docs/FRANK-AI-GUARDIAN.md §4). A SESSION lock can be
    talked down early; a MACHINE/serious lock never can. Every value here is a
    HARD bound the LLM advisor cannot cross — the model only advises a stance;
    these numbers decide the actual outcome, so a small model can't be talked
    into releasing Frank."""
    enabled: bool = True
    # Attempts per lockout before Frank stops entertaining pleas.
    max_attempts: int = 3
    # Must have served at least this fraction of the sentence before negotiating.
    min_served_fraction: float = 0.3
    # Even a perfectly-negotiated lock still serves at least this fraction — the
    # floor the end can never drop below. Frank always keeps the last word.
    floor_fraction: float = 0.5
    # A single accepted plea removes at most this fraction of the ORIGINAL
    # sentence (scaled by the advisor's sincerity score, clamped to the floor).
    per_attempt_reduction_fraction: float = 0.25


@dataclass
class CommentaryConfig:
    """Frank's voice (frankd/mistral.py). Operator direction: talking to the
    user is rule-based — the approved line bank in docs/FRANK-VOICE.md is
    the PRIMARY voice, not a fallback. AI phrasing is an opt-in garnish that
    needs both a key and this root-only flag."""
    ai_enabled: bool = False


@dataclass
class FrankConfig:
    sensitivity: int = 3               # 1 lenient … 5 strict (spec §5 default 3)
    enforcement: EnforcementConfig = field(default_factory=EnforcementConfig)
    triage: TriageConfig = field(default_factory=TriageConfig)
    overseer: OverseerConfig = field(default_factory=OverseerConfig)
    sift: SiftConfig = field(default_factory=SiftConfig)
    negotiation: NegotiationConfig = field(default_factory=NegotiationConfig)
    commentary: CommentaryConfig = field(default_factory=CommentaryConfig)
    ledger_path: Path = Path("/var/lib/frank/ledger.timestamps")
    incidents_path: Path = Path("/var/lib/frank/incidents.db")
    events_path: Path = Path("/var/lib/frank/events.log")
    triage_path: Path = Path("/var/lib/frank/triage.jsonl")
    verdicts_path: Path = Path("/var/lib/frank/verdicts.jsonl")
    ipc_socket: Path = Path("/run/frank/hub.sock")
    # Public login summary (usernames + expiry timestamps + bare violation
    # counts) so the login screen can refuse locked accounts and show each
    # account's count — docs/USERS.md.
    login_locks_path: Path = Path("/run/frank/login.locks")
    # Persistent per-user violation counts (frankd/violations.py) — survives
    # reboots and the daily reset; records follow the person.
    violations_path: Path = Path("/var/lib/frank/violations.json")
    reset_hour: int = 4                # daily reset time-of-day (context + ledger)

    def clamp_sensitivity(self, level: int) -> int:
        return max(1, min(5, int(level)))


def load(path: Path = DEFAULT_CONFIG) -> FrankConfig:
    """Load config from TOML, falling back to safe defaults if absent."""
    cfg = FrankConfig()
    if tomllib and path.exists():
        try:
            data = tomllib.loads(path.read_text())
        except Exception:
            return cfg
        if "sensitivity" in data:
            cfg.sensitivity = cfg.clamp_sensitivity(data["sensitivity"])
        enf = data.get("enforcement", {})
        if "warning_threshold" in enf:
            cfg.enforcement.warning_threshold = int(enf["warning_threshold"])
        if "hard_ceiling_seconds" in enf:
            cfg.enforcement.hard_ceiling_seconds = int(enf["hard_ceiling_seconds"])
        if "reset_hour" in data:
            cfg.reset_hour = int(data["reset_hour"])
        triage = data.get("triage", {})
        if "interval_seconds" in triage:
            cfg.triage.interval_seconds = int(triage["interval_seconds"])
        overseer = data.get("overseer", {})
        if "checkin_interval_seconds" in overseer:
            cfg.overseer.checkin_interval_seconds = int(overseer["checkin_interval_seconds"])
        if "wake_on_serious" in overseer:
            cfg.overseer.wake_on_serious = bool(overseer["wake_on_serious"])
        if "ai_enabled" in overseer:
            cfg.overseer.ai_enabled = bool(overseer["ai_enabled"])
        if "sift_confidence_threshold" in overseer:
            cfg.overseer.sift_confidence_threshold = float(overseer["sift_confidence_threshold"])
        for key in ("sift_elevated_count", "sift_serious_count", "slow_burn_count",
                    "burst_incident_count", "burst_distinct_rules"):
            if key in overseer:
                setattr(cfg.overseer, key, int(overseer[key]))
        sift = data.get("sift", {})
        if "backend" in sift:
            cfg.sift.backend = str(sift["backend"]).lower()
        if "base_url" in sift:
            cfg.sift.base_url = str(sift["base_url"])
        if "model" in sift:
            cfg.sift.model = str(sift["model"])
        if "confidence_threshold" in sift:
            cfg.sift.confidence_threshold = float(sift["confidence_threshold"])
        neg = data.get("negotiation", {})
        if "enabled" in neg:
            cfg.negotiation.enabled = bool(neg["enabled"])
        if "max_attempts" in neg:
            cfg.negotiation.max_attempts = int(neg["max_attempts"])
        for key in ("min_served_fraction", "floor_fraction",
                    "per_attempt_reduction_fraction"):
            if key in neg:
                setattr(cfg.negotiation, key, float(neg[key]))
        commentary = data.get("commentary", {})
        if "ai_enabled" in commentary:
            cfg.commentary.ai_enabled = bool(commentary["ai_enabled"])
    return cfg
