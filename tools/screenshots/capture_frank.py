#!/usr/bin/env python3
"""Capture Frank's surfaces: the root lockout screen + a populated ledger."""
import datetime
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _pty import Session, ENTER, DOWN                 # noqa: E402
from _render import render, RED                        # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).parent / "preview"


def lockout():
    end = int(time.time()) + 42 * 60 + 17             # ~42 min for a nice clock
    s = Session([str(REPO / "system/usr/local/bin/frank-locker"), str(end)],
                dict(os.environ, TERM="xterm-256color"))
    render(s.grid(), OUT / "12_lockout.png", fg=RED, frame=RED)
    print("wrote 12_lockout")
    s.close()


def populated_ledger():
    # Seed a timestamps-only ledger (24 entries) in a temp file and point the
    # Hub at it, then open Logs > Overseer Ledger.
    base = datetime.datetime.utcnow()
    lines = [(base - datetime.timedelta(minutes=7 * i)).strftime("%Y%m%dT%H%M%SZ")
             for i in range(24)][::-1]
    led = pathlib.Path(tempfile.mkstemp(suffix=".timestamps")[1])
    led.write_text("\n".join(lines) + "\n")
    env = dict(os.environ, TERM="xterm-256color",
               PYTHONPATH=str(REPO / "hub"),
               FOUNDATIONHUB_ETC=str(REPO / "system/etc/foundationhub"),
               FRANK_LEDGER=str(led))
    s = Session(["python3", "-m", "foundationhub"], env)
    s.drain(1.2)
    s.key(DOWN, 4); s.key(ENTER)     # -> Logs
    s.key(DOWN); s.key(ENTER)        # -> Overseer Ledger
    render(s.grid(), OUT / "13_ledger_populated.png")
    print("wrote 13_ledger_populated")
    s.close()
    led.unlink(missing_ok=True)


if __name__ == "__main__":
    lockout()
    populated_ledger()
