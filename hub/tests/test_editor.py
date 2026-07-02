"""Headless tests for the editor's Buffer (queue §1: buffer logic is a plain
class, no curses) and the soft-wrap helper."""
from foundationhub.editor import Buffer, wrap_segments


# ── construction / round-trip ─────────────────────────────────────────────────

def test_empty_buffer_has_one_line():
    buf = Buffer()
    assert buf.lines == [""]
    assert buf.text() == ""
    assert not buf.dirty


def test_text_round_trip():
    text = "# title\n\nbody line\n"
    assert Buffer(text).text() == text


# ── insert / newline ──────────────────────────────────────────────────────────

def test_insert_at_cursor():
    buf = Buffer("hello")
    buf.col = 5
    buf.insert("!")
    assert buf.text() == "hello!"
    assert buf.col == 6
    assert buf.dirty


def test_insert_mid_line():
    buf = Buffer("hlo")
    buf.col = 1
    buf.insert("el")
    assert buf.text() == "hello"
    assert buf.col == 3


def test_newline_splits_line():
    buf = Buffer("hello world")
    buf.col = 5
    buf.newline()
    assert buf.lines == ["hello", " world"]
    assert (buf.row, buf.col) == (1, 0)
    assert buf.dirty


def test_newline_at_end_appends_empty_line():
    buf = Buffer("abc")
    buf.move_end()
    buf.newline()
    assert buf.lines == ["abc", ""]


# ── backspace / delete ────────────────────────────────────────────────────────

def test_backspace_removes_char():
    buf = Buffer("abc")
    buf.col = 2
    buf.backspace()
    assert buf.text() == "ac"
    assert buf.col == 1


def test_backspace_at_line_start_joins_lines():
    buf = Buffer("ab\ncd")
    buf.row, buf.col = 1, 0
    buf.backspace()
    assert buf.lines == ["abcd"]
    assert (buf.row, buf.col) == (0, 2)


def test_backspace_at_origin_is_noop():
    buf = Buffer("abc")
    buf.backspace()
    assert buf.text() == "abc"
    assert not buf.dirty


def test_delete_removes_char_under_cursor():
    buf = Buffer("abc")
    buf.col = 1
    buf.delete()
    assert buf.text() == "ac"
    assert buf.col == 1


def test_delete_at_eol_joins_next_line():
    buf = Buffer("ab\ncd")
    buf.col = 2
    buf.delete()
    assert buf.lines == ["abcd"]


def test_delete_at_end_of_buffer_is_noop():
    buf = Buffer("ab")
    buf.col = 2
    buf.delete()
    assert buf.text() == "ab"
    assert not buf.dirty


# ── movement ──────────────────────────────────────────────────────────────────

def test_left_at_line_start_wraps_to_prev_eol():
    buf = Buffer("abc\nde")
    buf.row, buf.col = 1, 0
    buf.move_left()
    assert (buf.row, buf.col) == (0, 3)


def test_right_at_eol_wraps_to_next_line():
    buf = Buffer("abc\nde")
    buf.col = 3
    buf.move_right()
    assert (buf.row, buf.col) == (1, 0)


def test_vertical_move_clamps_column():
    buf = Buffer("a long line\nab")
    buf.col = 10
    buf.move_down()
    assert (buf.row, buf.col) == (1, 2)


def test_move_up_from_top_is_noop():
    buf = Buffer("abc")
    buf.col = 2
    buf.move_up()
    assert (buf.row, buf.col) == (0, 2)


def test_page_moves_clamp_to_buffer():
    buf = Buffer("\n".join(str(i) for i in range(10)))
    buf.move_page(100)
    assert buf.row == 9
    buf.move_page(-100)
    assert buf.row == 0


def test_home_end():
    buf = Buffer("hello")
    buf.col = 3
    buf.move_home()
    assert buf.col == 0
    buf.move_end()
    assert buf.col == 5


def test_movement_does_not_set_dirty():
    buf = Buffer("ab\ncd")
    buf.move_down()
    buf.move_right()
    buf.move_end()
    assert not buf.dirty


# ── soft wrap ─────────────────────────────────────────────────────────────────

def test_wrap_short_line_is_single_segment():
    assert wrap_segments("abc", 10) == ["abc"]


def test_wrap_splits_at_width():
    assert wrap_segments("abcdefgh", 3) == ["abc", "def", "gh"]


def test_wrap_exact_multiple_has_no_empty_tail():
    assert wrap_segments("abcdef", 3) == ["abc", "def"]


def test_wrap_empty_line():
    assert wrap_segments("", 5) == [""]


def test_wrap_degenerate_width():
    assert wrap_segments("abc", 0) == ["abc"]
