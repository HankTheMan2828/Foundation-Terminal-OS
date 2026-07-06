"""Data-source collectors (spec §6 — full scope, no exempt zones).

Each collector yields normalized `Event`s from a real signal:
  shell history · running processes & resource usage · filesystem activity ·
  network connections · browser searches/requests.

v1 status: these are working-but-minimal. Shell/process/network read real
system state via stdlib + standard CLIs. Filesystem and browser are wired as
pollers with clear [TODO(frank)] markers for the richer implementations
(inotify, browser history/DNS taps). The daemon polls collectors on an interval;
the rule engine (offline) classifies whatever they emit.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterator

from .model import Event, Source

try:
    import pwd
except ImportError:          # non-POSIX dev box
    pwd = None               # type: ignore[assignment]

OPERATOR = os.environ.get("FRANK_OPERATOR", "operator")


def operator_home() -> Path:
    """The operator's home, resolved from the system user database — never a
    guessed literal path, so the collectors work wherever this OS is installed
    (any distro's home layout, any mini PC). Override: FRANK_OPERATOR_HOME."""
    env = os.environ.get("FRANK_OPERATOR_HOME")
    if env:
        return Path(env)
    if pwd is not None:
        try:
            return Path(pwd.getpwnam(OPERATOR).pw_dir)
        except KeyError:
            pass
    return Path("/home") / OPERATOR   # last resort: the conventional layout

# The Hub publishes which logical account holds the session (docs/USERS.md);
# collectors stamp every event with it so records follow the person, not the
# shared Linux session user.
ACTIVE_USER_FILE = Path(os.environ.get("FOUNDATIONHUB_ACTIVE_USER",
                                       "/run/foundationhub/active-user"))


def active_user() -> str:
    try:
        return ACTIVE_USER_FILE.read_text().strip()
    except OSError:
        return ""

# Report-only activity spool the Hub appends to (hub/foundationhub/activity.py).
# This is the primary content source on a running machine: everything the user
# actually does happens inside the Hub, and there is no shell to leave a
# .bash_history behind. Frank OBSERVES this file; the Hub only appends to it and
# thereby gains no authority over Frank (same one-way relationship the shell's
# own history file has with shell_history). Default path is shared with the Hub
# (docs/ARCHITECTURE.md); FRANK_ACTIVITY_SPOOL overrides it for tests/off-target.
ACTIVITY_SPOOL = Path(os.environ.get(
    "FRANK_ACTIVITY_SPOOL",
    os.environ.get("FOUNDATIONHUB_ACTIVITY_LOG",
                   "/run/foundationhub/activity.log")))

# Operator-confirmed (docs/OPEN-QUESTIONS.md §3): 85% sustained for 10s. Streak
# is expressed in polls, not seconds, since the daemon's poll interval is what
# actually elapses between checks (default 2s -> 5 ticks == 10s).
RUNAWAY_CPU_THRESHOLD = 0.85     # fraction of one core
RUNAWAY_CPU_STREAK_TICKS = 5     # consecutive polls above threshold before flagging


def shell_history(state: dict) -> Iterator[Event]:
    """New lines appended to the operator's shell history since last poll."""
    hist = operator_home() / ".bash_history"
    try:
        lines = hist.read_text(errors="replace").splitlines()
    except OSError:
        return
    seen = state.get("shell_seen", 0)
    for line in lines[seen:]:
        if line.strip():
            yield Event(Source.SHELL, line.strip())
    state["shell_seen"] = len(lines)


def processes(state: dict) -> Iterator[Event]:
    """Running processes + CPU%. Sustained (not spiky) high CPU by a single
    process is a security signal: track consecutive high-CPU polls per-pid and
    emit the res-runaway-cpu rule's marker once a process has been hot for
    RUNAWAY_CPU_STREAK_TICKS in a row. A short burst resets the streak instead
    of flagging, so compiling/encoding/loading a game doesn't trip this."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,comm,pcpu", "--no-headers"],
            capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    streaks: dict[int, int] = state.setdefault("cpu_streaks", {})
    seen_pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid_s, comm, pcpu = parts
        try:
            pid = int(pid_s)
            cpu = float(pcpu) / 100.0
        except ValueError:
            continue
        seen_pids.add(pid)
        yield Event(Source.PROCESS, comm, meta={"cpu": cpu, "pid": pid})

        if cpu >= RUNAWAY_CPU_THRESHOLD:
            streaks[pid] = streaks.get(pid, 0) + 1
        else:
            streaks.pop(pid, None)
        if streaks.get(pid, 0) >= RUNAWAY_CPU_STREAK_TICKS:
            yield Event(Source.PROCESS, f"{comm} __RUNAWAY_CPU__",
                        meta={"cpu": cpu, "pid": pid})

    for pid in list(streaks):        # drop streaks for processes that exited
        if pid not in seen_pids:
            streaks.pop(pid, None)


def network(_state: dict) -> Iterator[Event]:
    """Active network connections (destinations)."""
    try:
        out = subprocess.run(["ss", "-tunp"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        return
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 5:
            yield Event(Source.NETWORK, f"connect {cols[4]}")


def filesystem(_state: dict) -> Iterator[Event]:
    """Files opened/edited. [TODO(frank)] replace poll stub with inotify watch."""
    return iter(())


def browser(_state: dict) -> Iterator[Event]:
    """Browser searches/requests. [TODO(frank)] tap history/DNS on target."""
    return iter(())


def activity(state: dict) -> Iterator[Event]:
    """Per-action reports the Hub appended to the activity spool since last poll.

    One JSON line per user action: {"ts", "user", "kind", "text"}. We yield each
    new line as an ACTIVITY event, preserving the reported user (so records
    follow the person even before collect() fills it in) and the reported ts (so
    the raw event log timestamps the action, not the poll). Cursor-by-line-count
    mirrors shell_history; malformed/blank lines are skipped, never fatal."""
    try:
        lines = ACTIVITY_SPOOL.read_text(errors="replace").splitlines()
    except OSError:
        return
    seen = state.get("activity_seen", 0)
    for line in lines[seen:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        text = str(rec.get("text", "")).strip()
        if not text:
            continue
        try:
            ts = float(rec.get("ts"))
        except (TypeError, ValueError):
            ts = None
        ev = Event(Source.ACTIVITY, text, user=str(rec.get("user", "")))
        if ts is not None:
            ev.ts = ts
        yield ev
    state["activity_seen"] = len(lines)


ALL = [shell_history, processes, network, filesystem, browser, activity]


def collect(state: dict) -> Iterator[Event]:
    user = active_user()
    for src in ALL:
        for event in src(state):
            if not event.user:
                event.user = user
            yield event
