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

import os
import subprocess
from pathlib import Path
from typing import Iterator

from .model import Event, Source

OPERATOR = os.environ.get("FRANK_OPERATOR", "operator")


def shell_history(state: dict) -> Iterator[Event]:
    """New lines appended to the operator's shell history since last poll."""
    hist = Path(f"/home/{OPERATOR}/.bash_history")
    try:
        lines = hist.read_text(errors="replace").splitlines()
    except OSError:
        return
    seen = state.get("shell_seen", 0)
    for line in lines[seen:]:
        if line.strip():
            yield Event(Source.SHELL, line.strip())
    state["shell_seen"] = len(lines)


def processes(_state: dict) -> Iterator[Event]:
    """Running processes + CPU%. Runaway resource usage is a security signal."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "comm,pcpu", "--no-headers"],
            capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        comm, pcpu = parts[0], parts[1]
        try:
            cpu = float(pcpu)
        except ValueError:
            continue
        yield Event(Source.PROCESS, comm, meta={"cpu": cpu / 100.0})


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


ALL = [shell_history, processes, network, filesystem, browser]


def collect(state: dict) -> Iterator[Event]:
    for src in ALL:
        yield from src(state)
