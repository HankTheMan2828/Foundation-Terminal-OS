"""Console text size (feedback #1): the kernel-VT bitmap font the whole Hub
draws in.

The text size is a VT-wide property set with ``setfont`` — curses cannot scale
a single app's glyphs — so it is applied once at session start by
``system/usr/local/bin/foundationhub-session`` and can be changed live from
Functions Control (Settings). The chosen face is persisted in one plain file,
``$FOUNDATIONHUB_ETC/console-font``, that both the bash session wrapper (reads
it at login) and this module (rewrites it live) share. On the target that file
is operator-writable (install/02), so an in-Hub change sticks across reboots
without a root helper.

The sizes are Terminus bitmap faces (the ``terminus-font`` package). The
operator asked for the default to be twice the original 8×16 face (``ter-v16b``)
— so the default is ``ter-v32b`` (16×32).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FontSize:
    label: str      # menu wording
    font: str       # setfont face name (Terminus)
    note: str       # cell geometry, for the live-status column


# Order here is the order shown in Settings.
SIZES: list[FontSize] = [
    FontSize("NORMAL", "ter-v16b", "8×16"),
    FontSize("LARGE", "ter-v24b", "12×24"),
    FontSize("EXTRA LARGE (2×)", "ter-v32b", "16×32"),
]

# 2× the original 8×16 face, per operator direction (feedback #1). The session
# wrapper hardcodes this same fallback so the two never disagree.
DEFAULT_FONT = "ter-v32b"


def config_path() -> Path:
    etc = os.environ.get("FOUNDATIONHUB_ETC", "/etc/foundationhub")
    return Path(etc) / "console-font"


def _by_font(font: str) -> FontSize | None:
    for s in SIZES:
        if s.font == font:
            return s
    return None


def get_font() -> str:
    """The persisted console face, or the default. Never raises; an unknown or
    missing value falls back to the default so a hand-edited file can't wedge
    the console."""
    try:
        val = config_path().read_text().strip()
    except OSError:
        val = ""
    return val if _by_font(val) else DEFAULT_FONT


def label_for(font: str) -> str:
    s = _by_font(font)
    return s.label if s else font


def current_label() -> str:
    """Live-status text for the FUNCTIONS menu row."""
    return label_for(get_font())


def save_font(font: str) -> bool:
    """Persist the chosen face. True on success. Best-effort: off-device
    FOUNDATIONHUB_ETC points somewhere writable; on the target the file is
    operator-owned (install/02)."""
    if _by_font(font) is None:
        return False
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(font + "\n")
        return True
    except OSError:
        return False


def apply_font(font: str) -> bool:
    """Run ``setfont`` on the current VT. True if it ran and succeeded (False
    off-device, where there is no kernel console to resize)."""
    if _by_font(font) is None or shutil.which("setfont") is None:
        return False
    try:
        res = subprocess.run(["setfont", font], capture_output=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def set_font(font: str) -> str:
    """Persist + apply, returning an operator-facing status string (never
    raises). The four outcomes are distinguished so the operator knows whether
    the change took now, at next login, or not at all."""
    s = _by_font(font)
    if s is None:
        return "unknown text size"
    saved = save_font(font)
    applied = apply_font(font)
    if applied and saved:
        return f"text size → {s.label}"
    if applied and not saved:
        return f"text size → {s.label} (this session only; persist needs a technician)"
    if saved and not applied:
        return f"text size → {s.label} (applies at next login)"
    return f"text size → {s.label} (off-device — no console to resize)"
