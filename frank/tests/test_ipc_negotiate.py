"""The `negotiate` IPC verb (docs/FRANK-LOCAL-AI.md §4).

`_handle` is exercised directly so this runs on platforms without AF_UNIX
(the socket-level tests in test_ipc.py don't). The point: negotiate is routed to
the handler, poll still works, and NOTHING else is ever accepted — the Hub gains
no authority over Frank.
"""
from pathlib import Path

from frankd.ipc import IPCServer


def test_negotiate_routes_to_handler():
    srv = IPCServer(Path("unused"), lambda: "NONE",
                    on_negotiate=lambda plea: f"got:{plea}")
    # maxsplit keeps the plea (with spaces) intact as one argument.
    assert srv._handle("negotiate I am sorry, truly") == "got:I am sorry, truly"


def test_poll_still_works():
    srv = IPCServer(Path("unused"), lambda: "pending-line",
                    on_negotiate=lambda plea: "x")
    assert srv._handle("poll") == "pending-line"


def test_negotiate_refused_when_no_handler():
    srv = IPCServer(Path("unused"), lambda: "NONE")   # no on_negotiate wired
    assert srv._handle("negotiate x") == "ERR read-only"


def test_no_mutating_command_is_accepted():
    srv = IPCServer(Path("unused"), lambda: "NONE",
                    on_negotiate=lambda plea: "x")
    for line in ("set_sensitivity 5", "disable", "stop", "config"):
        assert srv._handle(line) == "ERR read-only"
