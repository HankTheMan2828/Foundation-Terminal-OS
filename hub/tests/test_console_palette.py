"""Regression: the Hub must re-assert the VT phosphor palette itself.

The amber banner/nav and the games' contrast accents live in retuned VT palette
slots. The login shell (foundationhub-session) sets them once, but that retune
is clobbered when ncurses initialises color at Hub startup and when a child
curses program resets the console palette on exit — so before this fix the
accents only appeared after returning from a game. theme.dress_console() re-emits
the palette; __main__ calls it at startup and App.launch() after every child.
"""
import io

import pytest

from foundationhub import theme


def _emit(monkeypatch, term: str) -> str:
    buf = io.StringIO()
    monkeypatch.setenv("TERM", term)
    monkeypatch.setattr(theme.sys, "stdout", buf)
    theme.dress_console()
    return buf.getvalue()


def test_dresses_the_linux_console():
    with pytest.MonkeyPatch().context() as mp:
        out = _emit(mp, "linux")
    # It must set the amber base+bright slots (2/A) — the banner/nav colour.
    assert "\033]P2f59f00" in out
    assert "\033]PAffb42e" in out
    # ...and still the base yellow (slot 3) so the body text stays on-hue.
    assert "\033]P3ffff55" in out


def test_noop_off_the_vt():
    # On kitty / a dev terminal the palette comes from that terminal's config;
    # emitting \e]P there would just be stray bytes on screen.
    for term in ("xterm-256color", "kitty", ""):
        with pytest.MonkeyPatch().context() as mp:
            assert _emit(mp, term) == ""


def test_palette_matches_the_session_script(tmp_path):
    """dress_console() and the login shell must set byte-identical slots, or the
    two paths would drift and a screen could show two different ambers."""
    from pathlib import Path

    script = (Path(__file__).resolve().parents[2]
              / "system" / "usr" / "local" / "bin" / "foundationhub-session")
    text = script.read_text()
    for slot in ("P2f59f00", "PAffb42e", "P3ffff55", "P67fdfe0", "P7fff0c0"):
        assert slot in theme._VT_PALETTE
        assert slot in text
