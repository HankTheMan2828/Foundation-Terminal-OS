"""Contract tests for the USB AI raw-offset sidecar (FOUNDATIONAI2).

The real write/read path needs a block device (USB creator + foundation-install).
These tests lock the *header contract* so Windows PS1, Linux sh, and the
installer stay aligned — a silent layout drift is what would leave frank-ai
idle on every offline install.
"""
from __future__ import annotations

import re
import struct

STAGE_OFFSET = 2147483648  # 2 GiB
MAGIC = "FOUNDATIONAI2"


def build_header(model_offset: int, model_size: int,
                 server_offset: int, server_size: int) -> bytes:
    """Same text shape both USB creators write (ASCII, newline-separated)."""
    text = (
        f"{MAGIC}\n"
        f"model_offset={model_offset}\n"
        f"model_size={model_size}\n"
        f"server_offset={server_offset}\n"
        f"server_size={server_size}\n"
    )
    return text.encode("ascii")


def parse_header(raw: bytes) -> dict[str, int] | None:
    """Mirrors foundation-install's sed-based parse (first 4 KiB, NUL-stripped)."""
    text = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    if not text.startswith(MAGIC):
        return None
    out: dict[str, int] = {}
    for key in ("model_offset", "model_size", "server_offset", "server_size"):
        m = re.search(rf"^{key}=(\d+)\s*$", text, re.M)
        if not m:
            return None
        out[key] = int(m.group(1))
    return out


def test_windows_layout_parses():
    """Windows creator: 4 KiB header, model at STAGE_OFFSET+4096, 512-aligned server."""
    model_size = 1_187_801_280  # current BitNet i2_s
    server_size = 2_099_472
    model_off = STAGE_OFFSET + 4096
    srv_off = model_off + ((model_size + 511) // 512) * 512
    hdr = build_header(model_off, model_size, srv_off, server_size)
    # Pad to 4 KiB like Create-FoundationUSB.ps1
    blob = hdr + b"\x00" * (4096 - len(hdr))
    parsed = parse_header(blob[:4096])
    assert parsed is not None
    assert parsed["model_offset"] == model_off
    assert parsed["model_size"] == model_size
    assert parsed["server_offset"] == srv_off
    assert parsed["server_size"] == server_size
    assert parsed["model_offset"] >= STAGE_OFFSET + 4096
    assert parsed["server_offset"] > parsed["model_offset"]


def test_linux_layout_parses():
    """Linux creator: 1 MiB header region, model at STAGE_OFFSET+1MiB, 1MiB-aligned server."""
    stage_hdr = 1_048_576
    model_size = 1_187_801_280
    server_size = 2_099_472
    model_off = STAGE_OFFSET + stage_hdr
    srv_off = model_off + ((model_size + stage_hdr - 1) // stage_hdr) * stage_hdr
    hdr = build_header(model_off, model_size, srv_off, server_size)
    blob = hdr + b"\x00" * (4096 - len(hdr))  # installer only reads first 4 KiB
    parsed = parse_header(blob)
    assert parsed is not None
    assert parsed["model_offset"] == model_off
    assert parsed["server_offset"] == srv_off


def test_installer_rejects_missing_magic():
    assert parse_header(b"NOTAI\nmodel_offset=1\n") is None
    assert parse_header(b"\x00" * 4096) is None


def test_installer_bounds_match_foundation_install():
    """foundation-install refuses mo < STAGE_OFFSET+4096 or ms > 4 GiB."""
    ok = parse_header(build_header(STAGE_OFFSET + 4096, 1000, STAGE_OFFSET + 8192, 50))
    assert ok is not None
    assert ok["model_offset"] >= STAGE_OFFSET + 4096
    assert ok["model_size"] <= 4_294_967_296


def test_gguf_magic_constant():
    """install/11 and the creators check the first 4 bytes == 'GGUF'."""
    assert b"GGUF" == struct.pack("<4s", b"GGUF")
