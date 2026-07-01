#!/usr/bin/env python3
"""Capture the Home Hub screens from the REAL running zenhub app -> preview/."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from _pty import Session, ENTER, DOWN, BACK          # noqa: E402
from _render import render                            # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).parent / "preview"


def main():
    env = dict(os.environ, TERM="xterm-256color",
               PYTHONPATH=str(REPO / "hub"),
               ZENHUB_ETC=str(REPO / "system/etc/zenhub"))
    s = Session(["python3", "-m", "zenhub"], env)
    s.drain(1.4)

    def snap(name):
        render(s.grid(), OUT / f"{name}.png")
        print("wrote", name)

    snap("01_home")                                   # idx0 PROGRAMS
    s.key(ENTER); snap("02_programs"); s.key(BACK)
    s.key(DOWN); s.key(ENTER); snap("03_recreation"); s.key(BACK)   # idx1
    s.key(DOWN); s.key(ENTER); snap("04_functions")                 # idx2
    s.key(ENTER); snap("05_brightness"); s.key(BACK); s.key(BACK)
    s.key(DOWN); s.key(ENTER); snap("06_settings"); s.key(BACK)     # idx3
    s.key(DOWN); s.key(ENTER); snap("07_logs")                      # idx4
    s.key(DOWN); s.key(ENTER); snap("08_ledger"); s.key(BACK); s.key(BACK)
    s.key(DOWN); s.key(ENTER); snap("09_notes"); s.key(BACK)        # idx5
    s.key(DOWN); s.key(ENTER); snap("10_assistant"); s.key(BACK)    # idx6
    s.key(DOWN); s.key(ENTER); snap("11_power")                     # idx7
    s.close()


if __name__ == "__main__":
    main()
