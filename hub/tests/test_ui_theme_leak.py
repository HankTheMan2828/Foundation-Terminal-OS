"""Regression: the CRT chrome must not let a bold/alert background rendition
leak across redraws and lock the palette to a saturated "super amber"
(docs/FEEDBACK-FIRST-HARDWARE-RUN.md item 10).

A curses window background attribute is *sticky*: it survives erase() and its
rendition is combined into every character drawn afterwards. The whole Hub
draws onto one shared ``stdscr``, so ``full_screen_banner``'s old
``win.bkgd(" ", ... | A_BOLD)`` bled a bold rendition into every screen drawn
after it, and it never recovered. The fix has two halves, both guarded here:

  * ``full_screen_banner`` paints its background by filling rows explicitly,
    never via a sticky ``win.bkgd()``; and
  * ``draw_chrome`` re-asserts the normal phosphor background each frame, so any
    stray rendition left on the shared window heals on the next redraw.

The fake window below models exactly the sticky-background behaviour the real
bug depended on (verified against real curses under TERM=linux).
"""
import curses

import pytest

from foundationhub import theme, ui


class FakeWin:
    """curses-window stand-in modelling the sticky background: ``bkgd`` persists
    across ``erase`` and its rendition is OR'd into every cell written after."""

    def __init__(self, h: int = 24, w: int = 80):
        self.h, self.w = h, w
        self.bkgd_attr = 0
        self.cells: dict[tuple[int, int], int] = {}

    def bkgd(self, _ch, attr):
        self.bkgd_attr = attr

    def erase(self):
        pass  # erase() clears characters, NOT the background rendition

    def addstr(self, y, x, s, attr=0):
        for i in range(len(s)):
            self.cells[(y, x + i)] = attr | self.bkgd_attr

    def getmaxyx(self):
        return (self.h, self.w)

    # no-ops sufficient for draw_chrome / full_screen_banner
    def attron(self, _a): pass
    def attroff(self, _a): pass
    def border(self, *a): pass
    def hline(self, *a): pass
    def noutrefresh(self): pass


@pytest.fixture(autouse=True)
def _headless_curses(monkeypatch):
    # color_pair() and the ACS_* glyphs normally require initscr(); provide
    # headless stand-ins so theme.attr()/draw_chrome work without a terminal.
    # Model color_pair the way real curses does (pair number in the high bits)
    # so the A_BOLD bit — the thing under test — stays intact.
    monkeypatch.setattr(curses, "color_pair", lambda n: n << 8)
    monkeypatch.setattr(curses, "ACS_HLINE", ord("q"), raising=False)


def _bold(attr: int) -> bool:
    return bool(attr & curses.A_BOLD)


def test_full_screen_banner_does_not_set_a_sticky_background():
    win = FakeWin()
    ui.full_screen_banner(win, ["ALERT"], alert=True)
    # A bold sticky background here would bleed into every later screen.
    assert not _bold(win.bkgd_attr)


def test_draw_chrome_resets_a_poisoned_background():
    win = FakeWin()
    win.bkgd(" ", theme.attr(theme.PAIR_NORMAL, bold=True))  # poison it
    ui.draw_chrome(win, "TITLE")
    assert not _bold(win.bkgd_attr)


def test_body_text_renders_normal_weight_after_a_banner():
    win = FakeWin()
    # Frank raises a serious full-screen alert on the shared window...
    ui.full_screen_banner(win, ["SERIOUS"], alert=True)
    # ...and even if something leaves a bold background behind...
    win.bkgd(" ", theme.attr(theme.PAIR_ACCENT, bold=True))
    # ...the next Hub screen must draw ordinary body text at normal weight,
    # not the stuck "super amber".
    ui.draw_chrome(win, "HOME")
    win.addstr(6, 4, "body", theme.attr(theme.PAIR_NORMAL))
    assert not _bold(win.cells[(6, 4)])
