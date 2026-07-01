"""Persisted lockout state — the bridge from Frank (user `frank`) to the ROOT
enforcer that actually holds the console lock (spec §6).

Frank *decides* lockouts; it cannot, as an unprivileged user, forcibly lock the
operator's console. So it publishes the current lock decision to this file, and
a separate root service (frank-enforcer) reads it and applies an unbypassable
console lock. The operator can neither read nor write this file
(frank:frank 0640 — root reads, operator denied).

Two scope behaviors (spec §6):
  * session  lock is tied to the current console session; a reboot ends the
             session, so it is NOT re-applied on boot.
  * machine  lock persists across reboots — the enforcer re-applies it on boot
             until the timer expires, so rebooting cannot shorten it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .enforcement import Enforcer, Lockout, Scope
from .model import Severity


def write(path: Path, enforcer: Enforcer, now: float) -> None:
    """Publish the current lock decision for the root enforcer to apply."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lk = enforcer.lockout if enforcer.is_locked(now) else None
    if lk is None:
        data = {"active": False}
    else:
        data = {
            "active": True,
            "scope": lk.scope.value,
            "start": lk.start,
            "end": lk.end,
            "ceiling_end": lk.ceiling_end,
            "trigger_severity": lk.trigger_severity.name,
        }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)        # atomic publish
    try:
        os.chmod(path, 0o640)    # root + frank read; operator denied
    except OSError:
        pass


def read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"active": False}


def restore_machine_lock(enforcer: Enforcer, path: Path, now: float) -> None:
    """On daemon start, re-arm a still-valid MACHINE lock (spec §6).

    Session-scope locks are intentionally dropped (a reboot ends the session).
    Expired locks are dropped. This makes 'reboot to escape' work for session
    locks and NOT work for machine locks.
    """
    data = read(path)
    if not data.get("active"):
        return
    if data.get("scope") != Scope.MACHINE.value:
        return
    if now >= float(data.get("end", 0)):
        return
    enforcer.lockout = Lockout(
        scope=Scope.MACHINE,
        start=float(data["start"]),
        end=float(data["end"]),
        ceiling_end=float(data["ceiling_end"]),
        trigger_severity=Severity[data.get("trigger_severity", "SERIOUS")],
    )
