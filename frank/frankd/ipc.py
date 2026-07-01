"""The narrow Hub <-> Frank IPC surface (spec §5, §6).

Exactly three message types cross this boundary and nothing else:
  * poll                 (Hub -> Frank)  fetch a pending warn/lockout, if any
  * set_sensitivity N    (Hub -> Frank)  the ONE operator-tunable knob (1–5)
  * <warn/lockout lines> (Frank -> Hub)  delivered as the poll response

Deliberately tiny and line-oriented. The socket is group-restricted so only the
operator session can reach it; it exposes no way to read Frank's config, logs,
or findings, and no way to stop Frank (spec §6 config protection).
"""
from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Callable


class IPCServer:
    """A minimal AF_UNIX line server. Callbacks keep policy out of the transport."""

    def __init__(self, path: Path,
                 on_set_sensitivity: Callable[[int], str],
                 on_poll: Callable[[], str]):
        self.path = Path(path)
        self.on_set_sensitivity = on_set_sensitivity
        self.on_poll = on_poll
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        # Group-restricted: operator's group may connect; world may not.
        os.chmod(self.path, 0o660)
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                try:
                    data = conn.recv(256).decode().strip()
                    conn.sendall((self._handle(data) + "\n").encode())
                except OSError:
                    pass

    def _handle(self, line: str) -> str:
        parts = line.split()
        if not parts:
            return "ERR empty"
        cmd = parts[0]
        if cmd == "poll":
            return self.on_poll() or "NONE"
        if cmd == "set_sensitivity" and len(parts) == 2:
            try:
                return self.on_set_sensitivity(int(parts[1]))
            except ValueError:
                return "ERR bad value"
        # Anything else is out of scope for this boundary, by design.
        return "ERR unsupported"

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            self._sock.close()
        try:
            self.path.unlink()
        except OSError:
            pass
