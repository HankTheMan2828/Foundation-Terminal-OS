"""Frank — the overseer (spec §6).

Cold, procedural, always-on accountability layer. Watches real system usage,
classifies it with an offline rule engine (primary), optionally has Mistral
phrase the commentary on flagged/ambiguous events only, escalates warnings, and
enforces severity-scaled lockouts under a hard cooldown ceiling.

Runs as its own system user `frank`, isolated from the operator account
(spec §6 config protection). See docs/ARCHITECTURE.md.

Design invariants enforced in code (do not blur these):
  * severity → lockout DURATION
  * time-of-day → context/ledger RESET
  * the hard cooldown is an absolute CEILING Frank can approach but never exceed
  * the AI writes phrasing only; the rule layer decides what/how severe
  * the visible ledger is TIMESTAMPS ONLY
"""

__version__ = "0.1.1"
