"""The Hub<-Frank IPC must be strictly read-only (operator has no power, §6)."""
import socket
import time

from frankd.ipc import IPCServer


def _client(path, msg):
    for _ in range(50):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(str(path))
            break
        except OSError:
            time.sleep(0.02)
    else:
        raise AssertionError("server never came up")
    with s:
        s.sendall((msg + "\n").encode())
        return s.recv(256).decode().strip()


def test_poll_is_allowed(tmp_path):
    srv = IPCServer(tmp_path / "hub.sock", on_poll=lambda: "warn msg=hi")
    srv.start()
    try:
        assert _client(srv.path, "poll") == "warn msg=hi"
    finally:
        srv.stop()


def test_mutating_commands_are_refused(tmp_path):
    srv = IPCServer(tmp_path / "hub.sock", on_poll=lambda: "NONE")
    srv.start()
    try:
        # None of these may do anything — the operator cannot influence Frank.
        for hostile in (
            "set_sensitivity 5",
            "set_sensitivity 1",
            "disable",
            "stop",
            "config sensitivity=1",
            "unlock",
        ):
            assert _client(srv.path, hostile) == "ERR read-only", hostile
    finally:
        srv.stop()


def test_server_has_no_sensitivity_hook():
    # There is no constructor parameter or attribute to change Frank's settings.
    import inspect
    sig = inspect.signature(IPCServer.__init__)
    assert "on_set_sensitivity" not in sig.parameters
    assert not hasattr(IPCServer, "on_set_sensitivity")
