"""The Hub <-> Frank IPC surface (spec §6) — the Hub gets NO authority here.

The operator has NO power over Frank, ever. This boundary carries exactly one
direction of authority: Frank tells the Hub what to display, and — new this
pass — the Hub may *ask* Frank to reconsider a negotiable lockout. Asking is not
controlling: Frank decides, and can refuse (docs/FRANK-AI-GUARDIAN.md §4).

Accepted messages (Hub -> Frank):
  * poll                 fetch a pending warn/status line to display, if any
  * negotiate <plea>     submit a plea against a NEGOTIABLE lockout; Frank's
                         rule-bounded engine decides and returns the outcome.
                         Carries no identity — Frank attributes the plea to the
                         active-user file, so one user can't negotiate another's
                         lock. It cannot change config, thresholds, or verdicts.

Everything else — sensitivity, config, thresholds, enabling/disabling,
stopping — is rejected here and has no code path anywhere. There is no
`set_*` command. Sensitivity lives only in Frank's root-owned config and cannot
be changed from within the running OS by any user.

The socket is group-restricted so only the operator session can *connect* (to
receive warnings / submit a plea); connecting grants no authority beyond that.
"""
from __future__ import annotations

import os
import socket
import threading
from pathlib import Path
from typing import Callable


class IPCServer:
    """A minimal AF_UNIX line server. Frank -> Hub status, plus the read-only
    `negotiate` plea channel (Frank still decides everything)."""

    def __init__(self, path: Path, on_poll: Callable[[], str],
                 on_negotiate: Callable[[str], str] | None = None):
        self.path = Path(path)
        self.on_poll = on_poll
        self.on_negotiate = on_negotiate
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.path.unlink()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        # Group-restricted: the operator's group may connect to RECEIVE warnings.
        # Connecting confers no authority to change anything (see _handle).
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
        parts = line.split(maxsplit=1)
        if parts and parts[0] == "poll":
            return self.on_poll() or "NONE"
        if parts and parts[0] == "negotiate" and self.on_negotiate is not None:
            plea = parts[1] if len(parts) > 1 else ""
            return self.on_negotiate(plea) or "NONE"
        # There is deliberately NO mutating command. Anything else is refused.
        # The operator cannot tune, disable, or influence Frank from here.
        return "ERR read-only"

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            self._sock.close()
        try:
            self.path.unlink()
        except OSError:
            pass
