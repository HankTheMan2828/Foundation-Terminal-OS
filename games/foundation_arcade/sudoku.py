"""Sudoku — retires nudoku."""
from __future__ import annotations

import curses
import random

from . import chrome, engine, labels, scores

N = 9
BOX = 3
DEFAULT_CLUES = 32  # givens left on the board; lower = harder


def _valid(board: list[list[int]], row: int, col: int, val: int) -> bool:
    if any(board[row][c] == val for c in range(N) if c != col):
        return False
    if any(board[r][col] == val for r in range(N) if r != row):
        return False
    br, bc = (row // BOX) * BOX, (col // BOX) * BOX
    for r in range(br, br + BOX):
        for c in range(bc, bc + BOX):
            if (r, c) != (row, col) and board[r][c] == val:
                return False
    return True


def is_valid_placement(board: list[list[int]], row: int, col: int, val: int) -> bool:
    """Would placing `val` at (row, col) conflict with row/col/box? 0 = empty,
    always "valid" as a clear."""
    if val == 0:
        return True
    return _valid(board, row, col, val)


def _solve(board: list[list[int]], rng: random.Random) -> bool:
    for row in range(N):
        for col in range(N):
            if board[row][col] == 0:
                nums = list(range(1, N + 1))
                rng.shuffle(nums)
                for val in nums:
                    if _valid(board, row, col, val):
                        board[row][col] = val
                        if _solve(board, rng):
                            return True
                        board[row][col] = 0
                return False
    return True


def generate_solution(rng: random.Random | None = None) -> list[list[int]]:
    rng = rng or random.Random()
    board = [[0] * N for _ in range(N)]
    _solve(board, rng)
    return board


def generate_puzzle(rng: random.Random | None = None,
                     clues: int = DEFAULT_CLUES) -> tuple[list[list[int]], list[list[int]]]:
    """Returns (puzzle, solution). `puzzle` has `clues` cells filled, the
    rest zeroed; not guaranteed unique-solution (a casual terminal puzzle,
    not a setter's grid), but always solvable since it's a subset of a
    known-valid full board."""
    rng = rng or random.Random()
    solution = generate_solution(rng)
    puzzle = [row[:] for row in solution]
    cells = [(r, c) for r in range(N) for c in range(N)]
    rng.shuffle(cells)
    to_clear = max(0, N * N - clues)
    for r, c in cells[:to_clear]:
        puzzle[r][c] = 0
    return puzzle, solution


def is_complete(board: list[list[int]]) -> bool:
    if any(0 in row for row in board):
        return False
    for row in range(N):
        for col in range(N):
            if not _valid(board, row, col, board[row][col]):
                return False
    return True


class SudokuGame:
    def __init__(self, rng=None, clues: int = DEFAULT_CLUES):
        self.rng = rng or random.Random()
        self.puzzle, self.solution = generate_puzzle(self.rng, clues=clues)
        self.board = [row[:] for row in self.puzzle]
        self.row = 0
        self.col = 0

    def is_given(self, row: int, col: int) -> bool:
        return self.puzzle[row][col] != 0

    def set_cell(self, row: int, col: int, val: int) -> bool:
        if self.is_given(row, col):
            return False
        self.board[row][col] = val
        return True

    def move_cursor(self, d: tuple[int, int]) -> None:
        self.row = (self.row + d[0]) % N
        self.col = (self.col + d[1]) % N

    @property
    def solved(self) -> bool:
        return is_complete(self.board)


def run(win) -> int:
    game = SudokuGame()
    path = scores.scores_path()
    best = scores.best_score(path, labels.GAME_SUDOKU)
    win.nodelay(False)

    while True:
        top, left = chrome.draw_chrome(win, labels.GAME_SUDOKU, labels.SUDOKU_HINT)
        # N cells + 2 box-gap rows/double-cols (see _draw_board's gap_r/gap_c).
        top, left = chrome.draw_playfield(win, top, left, N + 2, N * 2 + 4)
        _draw_board(win, top, left, game)
        if game.solved:
            chrome.draw_statusbar(win, labels.SUDOKU_SOLVED)
        else:
            chrome.draw_statusbar(win, labels.SUDOKU_HINT)
        win.noutrefresh()
        curses.doupdate()

        if game.solved:
            score = DEFAULT_CLUES  # a completed puzzle is a completed puzzle
            scores.record_score(path, labels.GAME_SUDOKU, max(best, 1))
            _flash_end(win, labels.YOU_WIN)
            win.getch()
            return score

        key = win.getch()
        if key in engine.KEYS_QUIT:
            return 0
        d = engine.direction_for(key)
        if d is not None:
            game.move_cursor(d)
            continue
        if key in (curses.KEY_BACKSPACE, 127, 8, ord("0")):
            game.set_cell(game.row, game.col, 0)
        elif ord("1") <= key <= ord("9"):
            game.set_cell(game.row, game.col, key - ord("0"))


def _draw_board(win, top: int, left: int, game: SudokuGame) -> None:
    for r in range(N):
        for c in range(N):
            v = game.board[r][c]
            text = str(v) if v else "."
            selected = (r, c) == (game.row, game.col)
            given = game.is_given(r, c)
            conflict = v != 0 and not _cell_ok(game.board, r, c)
            if selected:
                a = chrome.attr(chrome.PAIR_HILITE, bold=True)
            elif conflict:
                a = chrome.attr(chrome.PAIR_WARN, bold=True)
            elif given:
                a = chrome.attr(chrome.PAIR_ACCENT, bold=True)
            else:
                a = chrome.attr(chrome.PAIR_NORMAL)
            gap_r = r // BOX
            gap_c = (c // BOX) * 2
            try:
                win.addstr(top + r + gap_r, left + c * 2 + gap_c, text, a)
            except curses.error:
                pass


def _cell_ok(board: list[list[int]], row: int, col: int) -> bool:
    val = board[row][col]
    if val == 0:
        return True
    board[row][col] = 0
    ok = _valid(board, row, col, val)
    board[row][col] = val
    return ok


def _flash_end(win, text: str) -> None:
    h, w = win.getmaxyx()
    try:
        win.addstr(h // 2, max(1, (w - len(text)) // 2), text,
                   chrome.attr(chrome.PAIR_ALERT, bold=True))
        win.addstr(h // 2 + 1, max(1, (w - len(labels.PRESS_CONTINUE)) // 2),
                   labels.PRESS_CONTINUE, chrome.attr(chrome.PAIR_DIM, dim=True))
    except curses.error:
        pass
    win.noutrefresh()
    curses.doupdate()
