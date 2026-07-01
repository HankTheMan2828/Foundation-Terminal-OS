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
class FrankConfig:
    sensitivity: int = 3               # 1 lenient … 5 strict (spec §5 default 3)
    enforcement: EnforcementConfig = field(default_factory=EnforcementConfig)
    ledger_path: Path = Path("/var/lib/frank/ledger.timestamps")
    incidents_path: Path = Path("/var/lib/frank/incidents.db")
    ipc_socket: Path = Path("/run/frank/hub.sock")
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
    return cfg
