"""Tiny pty driver: run a program, feed keystrokes, snapshot its screen grid.

Uses pyte as an in-process terminal emulator so we get the final character grid
the app drew, without needing a real display. Navigation uses single-byte vim
keys (j/k/h) — arrow CSI sequences and lone ESC are unreliable over a pty.
"""
from __future__ import annotations

import fcntl
import os
import pty
import select
import struct
import termios
import time

import pyte

from _render import COLS, ROWS

ENTER, DOWN, UP, BACK = b"\r", b"j", b"k", b"h"


class Session:
    def __init__(self, argv, env):
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.execvpe(argv[0], argv, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", ROWS, COLS, 0, 0))

    def drain(self, secs=0.45):
        end = time.time() + secs
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    return
                if not data:
                    return
                self.stream.feed(data)

    def key(self, k, n=1, delay=0.18):
        for _ in range(n):
            os.write(self.fd, k)
            time.sleep(delay)

    def grid(self):
        self.drain()
        return list(self.screen.display)

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass
