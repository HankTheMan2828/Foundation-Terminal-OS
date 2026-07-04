"""Regression: after a menu rebuild, the restored selection must settle on an
ENABLED row. The Notes home leads with a disabled section header ("— WORK —"),
and the old rebuild path (`menu.index = min(index, len-1)`) parked the
selection there — Enter silently did nothing until the operator pressed ↓.
`Menu.set_index` is the rebuild-restore path notes.py / files.py go through.
"""
from foundationhub.ui import Menu, MenuItem


def _notes_like_items():
    return [
        MenuItem("— WORK —", enabled=False),
        MenuItem("", enabled=False),
        MenuItem("--- create new note ---", lambda a: "new"),
        MenuItem("a-note", lambda a: "open"),
    ]


def test_set_index_zero_skips_leading_disabled_header():
    menu = Menu(_notes_like_items())
    menu.set_index(0)                      # the rebuild-restore of a fresh screen
    assert menu.items[menu.index].enabled
    assert menu.index == 2                 # lands on create-new, not the header


def test_set_index_keeps_an_enabled_selection():
    menu = Menu(_notes_like_items())
    menu.set_index(3)
    assert menu.index == 3


def test_set_index_clamps_out_of_range():
    menu = Menu(_notes_like_items())
    menu.set_index(99)
    assert menu.index == 3                 # last row, which is enabled


def test_set_index_on_empty_menu_is_safe():
    menu = Menu([])
    menu.set_index(5)
    assert menu.index == 0
