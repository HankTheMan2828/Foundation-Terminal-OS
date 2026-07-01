"""Core domain types shared across Frank: severity, tracks, events, findings."""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class Track(enum.Enum):
    """The two category tracks (spec §6), each with its own severity tiers."""
    SECURITY = "security"           # malware, exploit tooling, creds, runaway resources
    LEGAL_ETHICAL = "legal_ethical" # broader concerning content/activity


class Severity(enum.IntEnum):
    """Severity tiers. IntEnum so comparisons/max() are meaningful."""
    MINOR = 1
    ELEVATED = 2
    SERIOUS = 3


class Source(enum.Enum):
    """Where an observed event came from (spec §6 data sources — full scope)."""
    SHELL = "shell"          # shell/command history
    PROCESS = "process"      # running processes & resource usage
    FILESYSTEM = "filesystem"  # files opened/edited
    NETWORK = "network"      # connections/destinations
    BROWSER = "browser"      # searches/requests from the browser & elsewhere


@dataclass
class Event:
    """A single normalized observation from a data source."""
    source: Source
    text: str                       # the observable payload (command, path, host, query…)
    ts: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)  # e.g. {"cpu": 0.98, "pid": 1234}


@dataclass
class Finding:
    """A rule match against an event. The rule layer — not the AI — produces this."""
    rule_id: str
    track: Track
    severity: Severity
    event: Event
    matched: str                    # what matched (kept frank-only; never shown to user)
    description: str = ""           # rule's own description (frank-only)

    def redacted_descriptor(self) -> str:
        """A *non-revealing* descriptor for the AI layer.

        Spec §6: the user must never see specifics, and the AI writes phrasing
        without being handed exploitable detail either — it gets track +
        severity + source, never the matched content.
        """
        return f"{self.track.value}/{self.severity.name.lower()} from {self.event.source.value}"
