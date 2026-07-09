"""Curses front-end: start menu, the board, cursor selection, promotion picker,
Esc menu, and driving the AI. All the rules live in `board.py` and all the
opponent logic in `ai.py`; this file only draws and dispatches input, in the
shared Fallout/Aperture register (highlight a square, press Enter).
"""
from __future__ import annotations

import curses

from . import ai, chrome, labels, stats
from . import board as B

# Movement keys agree across arrows / WASD / vim hjkl, same as the arcade.
_UP = {curses.KEY_UP, ord("w"), ord("W"), ord("k")}
_DOWN = {curses.KEY_DOWN, ord("s"), ord("S"), ord("j")}
_LEFT = {curses.KEY_LEFT, ord("a"), ord("A"), ord("h")}
_RIGHT = {curses.KEY_RIGHT, ord("d"), ord("D"), ord("l")}
_ENTER = {curses.KEY_ENTER, ord("\n"), ord("\r"), ord(" ")}
_ESCAPE = {27, ord("q"), ord("Q")}

_CELL_W = 3          # each square is 3 columns wide: " K "
_MIN_H, _MIN_W = 16, 34


def main(stdscr) -> None:
    """Entry point (via curses.wrapper). Loops: start menu -> play -> menu."""
    curses.set_escdelay(25)  # default ~1000ms made Esc feel laggy vs. Backspace
    chrome.init(stdscr)
    curses.curs_set(0)
    stdscr.keypad(True)
    while True:
        choice = _start_menu(stdscr)
        if choice is None:
            return
        human_side, depth = choice
        action = _play(stdscr, human_side, depth)
        if action == "quit":
            return
        # "menu" -> fall through and show the start menu again.


# -- start menu -------------------------------------------------------------

def _start_menu(win):
    """Pick side + difficulty. Returns (human_side, depth) or None to quit."""
    sides = [(B.WHITE, labels.SIDE_WHITE), (B.BLACK, labels.SIDE_BLACK)]
    diffs = [("EASY", labels.DIFF_EASY), ("NORMAL", labels.DIFF_NORMAL)]
    side_i, diff_i, row = 0, 0, 0        # row 0=side, 1=difficulty, 2=begin
    win.nodelay(False)
    while True:
        top, left = chrome.draw_chrome(win, labels.CHESS_TITLE, labels.CHESS_TAGLINE)
        rows = [
            (labels.MENU_SIDE, sides[side_i][1]),
            (labels.MENU_DIFFICULTY, diffs[diff_i][1]),
            (labels.MENU_BEGIN, ""),
        ]
        for i, (lbl, val) in enumerate(rows):
            selected = i == row
            a = chrome.attr(chrome.PAIR_HILITE, bold=True) if selected \
                else chrome.attr(chrome.PAIR_NORMAL)
            text = f"  {lbl}: {val}  " if val else f"  {lbl}  "
            _safe(win, top + 1 + i * 2, left, text.ljust(40), a)
        chrome.draw_statusbar(win, labels.MENU_HINT)
        win.noutrefresh()
        curses.doupdate()

        key = win.getch()
        if key in _ESCAPE:
            return None
        elif key in _UP:
            row = (row - 1) % 3
        elif key in _DOWN:
            row = (row + 1) % 3
        elif key in _LEFT or key in _RIGHT:
            step = -1 if key in _LEFT else 1
            if row == 0:
                side_i = (side_i + step) % len(sides)
            elif row == 1:
                diff_i = (diff_i + step) % len(diffs)
        elif key in _ENTER:
            if row == 2:
                return (sides[side_i][0], ai.DEPTHS[diffs[diff_i][0]])


# -- gameplay ---------------------------------------------------------------

def _play(win, human_side: str, depth: int) -> str:
    """Play one game. Returns 'menu' (back to start menu) or 'quit'."""
    board = B.Board.initial()
    flip = human_side == B.BLACK       # keep the operator's pieces at the bottom
    cursor = [6, 4] if human_side == B.WHITE else [1, 4]
    selected = None
    targets: dict = {}                 # dest (r,c) -> list[Move] for the selection
    last_move = None
    path = stats.stats_path()
    record = stats.load_record(path)

    win.nodelay(False)

    # If the operator took Black, the machine (White) opens.
    if board.turn != human_side:
        _render(win, board, human_side, flip, cursor, selected, targets,
                last_move, record, thinking=True)
        board, last_move = _ai_move(board, depth)

    while True:
        state = B.status(board)
        _render(win, board, human_side, flip, cursor, selected, targets,
                last_move, record, thinking=False)

        if B.is_game_over(board):
            outcome = _finish(win, board, human_side, state, path)
            record = stats.load_record(path)
            # Show the terminal position with the result, then wait and exit.
            _render(win, board, human_side, flip, cursor, None, {},
                    last_move, record, thinking=False, result=outcome)
            win.getch()
            return "menu"

        key = win.getch()
        if key in _ESCAPE:
            action = _esc_menu(win)
            if action == "quit":
                return "quit"
            if action == "new":
                return "menu"
            if action == "resign":
                stats.record_result(path, stats.LOSS)
                record = stats.load_record(path)
                _render(win, board, human_side, flip, cursor, None, {},
                        last_move, record, thinking=False, result=labels.RESULT_RESIGN)
                win.getch()
                return "menu"
            continue  # resume

        moved = _handle_key(key, board, human_side, flip, cursor, selected, targets)
        selected, targets, played = moved
        if played is not None:
            board = played
            last_move = _last
            # Hand over to the machine unless the game just ended.
            if not B.is_game_over(board):
                _render(win, board, human_side, flip, cursor, None, {},
                        last_move, record, thinking=True)
                board, last_move = _ai_move(board, depth)
            selected, targets = None, {}


# `_handle_key` returns the move it applied via this module-level slot to keep
# its return tuple small; only ever read immediately after it's set.
_last = None


def _handle_key(key, board, human_side, flip, cursor, selected, targets):
    """Process one keypress during the operator's turn. Returns
    (selected, targets, applied_board_or_None)."""
    global _last
    dr = dc = 0
    if key in _UP:
        dr = 1 if flip else -1
    elif key in _DOWN:
        dr = -1 if flip else 1
    elif key in _LEFT:
        dc = 1 if flip else -1
    elif key in _RIGHT:
        dc = -1 if flip else 1
    if dr or dc:
        cursor[0] = max(0, min(7, cursor[0] + dr))
        cursor[1] = max(0, min(7, cursor[1] + dc))
        return selected, targets, None

    if key not in _ENTER:
        return selected, targets, None

    sq = (cursor[0], cursor[1])
    piece = board.grid[sq[0]][sq[1]]
    own = B.color_of(piece) == human_side

    if selected is None:
        if own:
            new_targets = _targets_for(board, sq)
            if new_targets:
                return sq, new_targets, None
        return None, {}, None

    if sq == selected:
        return None, {}, None            # click the same square to cancel
    if sq in targets:
        moves = targets[sq]
        mv = moves[0]
        if len(moves) > 1:               # promotion: several moves, same dest
            promo = _pick_promotion(_screen)
            mv = next((m for m in moves if m.promo == promo), moves[0])
        _last = mv
        return None, {}, B.make_move(board, mv)
    if own:                              # switch selection to another own piece
        new_targets = _targets_for(board, sq)
        if new_targets:
            return sq, new_targets, None
        return None, {}, None
    return None, {}, None                # empty/enemy non-target: cancel


def _targets_for(board, sq) -> dict:
    out: dict = {}
    for mv in B.legal_moves(board):
        if mv.frm == sq:
            out.setdefault(mv.to, []).append(mv)
    return out


def _ai_move(board, depth):
    mv = ai.best_move(board, depth=depth)
    if mv is None:
        return board, None
    return B.make_move(board, mv), mv


def _finish(win, board, human_side, state, path) -> str:
    """Record the result and return the banner text for it."""
    if state == B.CHECKMATE:
        # The side to move is the one that's been mated.
        if board.turn == human_side:
            stats.record_result(path, stats.LOSS)
            return labels.RESULT_LOSS
        stats.record_result(path, stats.WIN)
        return labels.RESULT_WIN
    if state == B.STALEMATE:
        stats.record_result(path, stats.DRAW)
        return labels.RESULT_STALEMATE
    if state == B.DRAW_50:
        stats.record_result(path, stats.DRAW)
        return labels.RESULT_DRAW_50
    stats.record_result(path, stats.DRAW)
    return labels.RESULT_DRAW_MATERIAL


# -- rendering --------------------------------------------------------------

# Stash the window so the promotion picker (reached from _handle_key) can draw.
_screen = None

# Single-letter piece glyphs; case already tells White (upper) from Black.
_GLYPH = {"P": "P", "N": "N", "B": "B", "R": "R", "Q": "Q", "K": "K"}


def _render(win, board, human_side, flip, cursor, selected, targets,
            last_move, record, *, thinking: bool, result: str | None = None):
    global _screen
    _screen = win
    h, w = win.getmaxyx()
    if h < _MIN_H or w < _MIN_W:
        win.erase()
        _safe(win, 0, 0, labels.TOO_SMALL, chrome.attr(chrome.PAIR_WARN, bold=True))
        win.noutrefresh()
        curses.doupdate()
        return

    state = B.status(board)
    top, left = chrome.draw_chrome(win, labels.CHESS_TITLE)
    b_left = left
    check_sq = board.king_square(board.turn) if state in (B.CHECK, B.CHECKMATE) else None

    for srow in range(8):
        r = (7 - srow) if flip else srow
        _safe(win, top + srow, b_left, str(8 - r),
              chrome.attr(chrome.PAIR_DIM, dim=True))
        for scol in range(8):
            c = (7 - scol) if flip else scol
            x = b_left + 2 + scol * _CELL_W
            _draw_cell(win, top + srow, x, board, (r, c),
                       cursor, selected, targets, check_sq)
    # File letters under the board.
    for scol in range(8):
        c = (7 - scol) if flip else scol
        _safe(win, top + 8, b_left + 2 + scol * _CELL_W + 1, B._FILES[c],
              chrome.attr(chrome.PAIR_DIM, dim=True))

    _draw_sidepanel(win, top, b_left + 2 + 8 * _CELL_W + 2, w, human_side,
                    board, last_move, record, thinking, state, result)

    if result:
        chrome.draw_statusbar(win, labels.PRESS_CONTINUE)
    elif thinking:
        chrome.draw_statusbar(win, labels.THINKING)
    else:
        chrome.draw_statusbar(win, labels.HINT_MOVE)
    win.noutrefresh()
    curses.doupdate()


def _draw_cell(win, y, x, board, sq, cursor, selected, targets, check_sq):
    r, c = sq
    piece = board.grid[r][c]
    is_cursor = [r, c] == list(cursor)
    is_selected = sq == selected
    is_target = sq in targets

    if piece != B.EMPTY:
        glyph = _GLYPH[piece.upper()]
        if is_cursor or is_selected:
            a = chrome.attr(chrome.PAIR_HILITE, bold=True)
        elif sq == check_sq:
            a = chrome.attr(chrome.PAIR_ALERT, bold=True)
        elif is_target:                              # a capture the cursor offers
            a = chrome.attr(chrome.PAIR_WARN, bold=True)
        elif piece in B.WHITE_PIECES:
            a = chrome.attr(chrome.PAIR_BRIGHT, bold=True)   # cream white
        else:
            a = chrome.attr(chrome.PAIR_AMBER, bold=True)    # amber = "dark" side
        text = f" {glyph} "
    else:
        if is_cursor:
            text, a = " + ", chrome.attr(chrome.PAIR_HILITE, bold=True)
        elif is_target:
            text, a = " * ", chrome.attr(chrome.PAIR_ACCENT, bold=True)
        else:
            text, a = " . ", chrome.attr(chrome.PAIR_DIM, dim=True)
    _safe(win, y, x, text, a)


def _draw_sidepanel(win, top, x, w, human_side, board, last_move, record,
                    thinking, state, result):
    if x > w - 12:
        return  # too narrow for the panel; the status bar carries the essentials
    lines = []
    if result:
        lines.append((result, chrome.attr(chrome.PAIR_ACCENT, bold=True)))
    elif thinking:
        lines.append((labels.THINKING, chrome.attr(chrome.PAIR_WARN)))
    else:
        turn = labels.YOUR_MOVE if board.turn == human_side else labels.THINKING
        lines.append((turn, chrome.attr(chrome.PAIR_ACCENT, bold=True)))
    if state in (B.CHECK, B.CHECKMATE) and not result:
        lines.append((labels.IN_CHECK, chrome.attr(chrome.PAIR_ALERT, bold=True)))
    if last_move is not None:
        lines.append((f"{labels.LAST} {last_move.uci()}",
                      chrome.attr(chrome.PAIR_DIM, dim=True)))
    lines.append(("", 0))
    lines.append((labels.RECORD, chrome.attr(chrome.PAIR_DIM, dim=True)))
    lines.append((labels.RECORD_FMT.format(w=record[stats.WIN], l=record[stats.LOSS],
                                           d=record[stats.DRAW]),
                  chrome.attr(chrome.PAIR_NORMAL)))
    for i, (text, a) in enumerate(lines):
        if text:
            _safe(win, top + i, x, text[: w - x - 1], a)


# -- overlays ---------------------------------------------------------------

def _pick_promotion(win) -> str:
    """Modal picker for a promoting pawn. Returns 'Q'/'R'/'B'/'N' (default Q)."""
    opts = [("Q", labels.PROMOTE_Q), ("R", labels.PROMOTE_R),
            ("B", labels.PROMOTE_B), ("N", labels.PROMOTE_N)]
    i = 0
    while True:
        _overlay(win, labels.PROMOTE_PROMPT,
                 [(o[1], j == i) for j, o in enumerate(opts)])
        key = win.getch()
        if key in _UP or key in _LEFT:
            i = (i - 1) % len(opts)
        elif key in _DOWN or key in _RIGHT:
            i = (i + 1) % len(opts)
        elif key in _ENTER:
            return opts[i][0]


def _esc_menu(win) -> str:
    opts = [("resume", labels.ESC_RESUME), ("new", labels.ESC_NEWGAME),
            ("resign", labels.ESC_RESIGN), ("quit", labels.ESC_QUIT)]
    i = 0
    while True:
        _overlay(win, labels.ESC_TITLE, [(o[1], j == i) for j, o in enumerate(opts)])
        key = win.getch()
        if key in _UP:
            i = (i - 1) % len(opts)
        elif key in _DOWN:
            i = (i + 1) % len(opts)
        elif key in _ENTER:
            return opts[i][0]
        elif key in _ESCAPE:
            return "resume"


def _overlay(win, title: str, rows) -> None:
    """A small centered menu box drawn over the current board."""
    h, w = win.getmaxyx()
    box_w = max(len(title), max((len(t) for t, _ in rows), default=0)) + 6
    box_h = len(rows) + 4
    y0 = max(0, (h - box_h) // 2)
    x0 = max(0, (w - box_w) // 2)
    for dy in range(box_h):
        _safe(win, y0 + dy, x0, " " * box_w, chrome.attr(chrome.PAIR_NORMAL))
    _safe(win, y0, x0, "+" + "-" * (box_w - 2) + "+", chrome.attr(chrome.PAIR_ACCENT))
    _safe(win, y0 + box_h - 1, x0, "+" + "-" * (box_w - 2) + "+",
          chrome.attr(chrome.PAIR_ACCENT))
    _safe(win, y0 + 1, x0 + (box_w - len(title)) // 2, title,
          chrome.attr(chrome.PAIR_ACCENT, bold=True))
    for j, (text, sel) in enumerate(rows):
        a = chrome.attr(chrome.PAIR_HILITE, bold=True) if sel \
            else chrome.attr(chrome.PAIR_NORMAL)
        label = f" {text} " if sel else f"  {text}"
        _safe(win, y0 + 3 + j, x0 + 2, label.ljust(box_w - 4), a)
    win.noutrefresh()
    curses.doupdate()


def _safe(win, y, x, text, a) -> None:
    try:
        win.addstr(y, x, text, a)
    except curses.error:
        pass
