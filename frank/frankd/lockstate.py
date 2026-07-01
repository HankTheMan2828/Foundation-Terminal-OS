"""Persisted lockout state — the bridge from Frank (user `frank`) to the ROOT
enforcer that actually holds the console lock (spec §6).

Frank *decides* lockouts; it cannot, as an unprivileged user, forcibly lock the
operator's console. So it publishes the current lock decision to this file, and
a separate root service (frank-enforcer) reads it and applies an unbypassable
console lock. The operator can neither read nor write this file
(frank:frank 0640 — root reads, operator denied).

Multi-user (docs/USERS.md): records follow the person, machine locks are
global. The v2 schema therefore has three parts:

  * flat summary  ("active"/"scope"/"end") — what the root enforcer keys its
                  console action on. Machine scope wins over session scope.
  * "machine"     the active machine lock + which user triggered it, if any.
                  Persists across reboots — the enforcer re-applies it on boot
                  until the timer expires, so rebooting cannot shorten it.
  * "sessions"    active session locks by user. A reboot ends the session, so
                  these are NOT re-applied on boot; instead they gate the LOGIN
                  screen — the locked account can't sign back in until expiry.

A second, PUBLIC file (write_public) carries only usernames + expiry
timestamps so the operator-owned login screen can refuse locked accounts —
same disclosure philosophy as the timestamp-only ledger: when, never why.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .enforcement import Lockout, Scope, UserEnforcers
from .model import Severity


def _lock_record(lk: Lockout) -> dict:
    return {
        "start": lk.start,
        "end": lk.end,
        "ceiling_end": lk.ceiling_end,
        "trigger_severity": lk.trigger_severity.name,
    }


def write(path: Path, enforcers: UserEnforcers, now: float) -> None:
    """Publish the current lock decision for the root enforcer to apply."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    machine = enforcers.machine_lockout(now)
    sessions = enforcers.session_lockouts(now)
    if machine is not None:
        user, lk = machine
        summary = {"active": True, "scope": Scope.MACHINE.value, "end": lk.end}
        machine_data = {"user": user, **_lock_record(lk)}
    elif sessions:
        summary = {"active": True, "scope": Scope.SESSION.value,
                   "end": max(lk.end for lk in sessions.values())}
        machine_data = None
    else:
        summary = {"active": False}
        machine_data = None
    data = {
        "version": 2,
        **summary,
        "machine": machine_data,
        "sessions": {user: _lock_record(lk) for user, lk in sessions.items()},
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)        # atomic publish
    try:
        os.chmod(path, 0o640)    # root + frank read; operator denied
    except OSError:
        pass


def write_public(path: Path, enforcers: UserEnforcers, now: float) -> None:
    """The login screen's view: usernames + expiry timestamps ONLY (§6 —
    when, never why). World-readable by design; there is nothing here the
    ledger doesn't already disclose."""
    path = Path(path)
    machine = enforcers.machine_lockout(now)
    data = {
        "machine_end": machine[1].end if machine else 0,
        "users": {user: lk.end
                  for user, lk in enforcers.session_lockouts(now).items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)
        os.chmod(path, 0o644)
    except OSError:
        pass   # /run may not exist off-device; the login screen degrades to open


def read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"active": False}


def restore_machine_lock(enforcers: UserEnforcers, path: Path, now: float) -> None:
    """On daemon start, re-arm a still-valid MACHINE lock (spec §6).

    Session-scope locks are intentionally dropped (a reboot ends the session).
    Expired locks are dropped. This makes 'reboot to escape' work for session
    locks and NOT work for machine locks. The lock is re-armed onto the user
    who triggered it, so their record stays accurate.
    """
    data = read(path)
    machine = data.get("machine")
    if not machine:
        return
    if now >= float(machine.get("end", 0)):
        return
    enforcers.enforcer_for(machine.get("user", "")).lockout = Lockout(
        scope=Scope.MACHINE,
        start=float(machine["start"]),
        end=float(machine["end"]),
        ceiling_end=float(machine["ceiling_end"]),
        trigger_severity=Severity[machine.get("trigger_severity", "SERIOUS")],
    )
