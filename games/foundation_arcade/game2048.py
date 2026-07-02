"""2048 — retires the `2048` package."""
from __future__ import annotations

import curses
import random

from . import chrome, engine, labels, scores

SIZE = 4


def _compress_merge(line: list[int]) -> tuple[list[int], int]:
    """Slide a single row/column left, merging equal neighbors once each.
    Returns (new_line, score_gained)."""
    vals = [v for v in line if v]
    merged: list[int] = []
    gained = 0
    i = 0
    while i < len(vals):
        if i + 1 < len(vals) and vals[i] == vals[i + 1]:
            merged.append(vals[i] * 2)
            gained += vals[i] * 2
            i += 2
        else:
            merged.append(vals[i])
            i += 1
    merged += [0] * (len(line) - len(merged))
    return merged, gained


class Game2048:
    """Pure logic: board, moves, spawns. No curses, no game loop timing —
    2048 advances on keypress, not on a clock."""

    def __init__(self, size: int = SIZE, rng=None):
        self.size = size
        self.rng = rng or random.Random()
        self.board = [[0] * size for _ in range(size)]
        self.score = 0
        self._spawn()
        self._spawn()

    def _empty_cells(self) -> list[tuple[int, int]]:
        return [(r, c) for r in range(self.size) for c in range(self.size)
                if not self.board[r][c]]

    def _spawn(self) -> None:
        empties = self._empty_cells()
        if not empties:
            return
        r, c = self.rng.choice(empties)
        self.board[r][c] = 4 if self.rng.random() < 0.1 else 2

    def _rotated(self, times: int) -> list[list[int]]:
        b = self.board
        for _ in range(times % 4):
            b = [list(row) for row in zip(*b[::-1])]
        return b

    def move(self, direction: tuple[int, int]) -> bool:
        """direction is one of engine.DIR_*. Returns True if the board
        changed (and a new tile was spawned)."""
        # Reduce every direction to "merge left" by rotating the board,
        # merging, then rotating back.
        rot = {engine.DIR_LEFT: 0, engine.DIR_UP: 1,
               engine.DIR_RIGHT: 2, engine.DIR_DOWN: 3}[direction]
        board = self._rotated(rot)
        new_board = []
        gained = 0
        changed = False
        for row in board:
            new_row, g = _compress_merge(row)
            if new_row != row:
                changed = True
            gained += g
            new_board.append(new_row)
        if not changed:
            return False
        # rotate back: original was rotated `rot` times CW; undo with (4-rot)
        result = new_board
        for _ in range((4 - rot) % 4):
            result = [list(row) for row in zip(*result[::-1])]
        self.board = result
        self.score += gained
        self._spawn()
        return True

    def is_game_over(self) -> bool:
        if self._empty_cells():
            return False
        for r in range(self.size):
            for c in range(self.size):
                v = self.board[r][c]
                if c + 1 < self.size and self.board[r][c + 1] == v:
                    return False
                if r + 1 < self.size and self.board[r + 1][c] == v:
                    return False
        return True

    def has_won(self) -> bool:
        return any(v >= 2048 for row in self.board for v in row)


def run(win) -> int:
    game = Game2048()
    path = scores.scores_path()
    best = scores.best_score(path, labels.GAME_2048)
    win.nodelay(False)
    won_shown = False

    while True:
        top, left = chrome.draw_chrome(win, labels.GAME_2048)
        _draw_board(win, top, left, game)
        chrome.draw_statusbar(
            win, f"{labels.SCORE} {game.score}   {labels.BEST} {max(best, game.score)}")
        win.noutrefresh()
        curses.doupdate()

        if game.has_won() and not won_shown:
            won_shown = True
            scores.record_score(path, labels.GAME_2048, game.score)
            _flash_end(win, labels.YOU_WIN)
            win.getch()
        if game.is_game_over():
            scores.record_score(path, labels.GAME_2048, game.score)
            _flash_end(win, labels.GAME_OVER)
            win.getch()
            break

        key = win.getch()
        if key in engine.KEYS_QUIT:
            break
        d = engine.direction_for(key)
        if d is not None:
            game.move(d)

    return game.score


def _draw_board(win, top: int, left: int, game: Game2048) -> None:
    for r in range(game.size):
        for c in range(game.size):
            v = game.board[r][c]
            text = str(v) if v else "."
            a = chrome.attr(chrome.PAIR_HILITE if v else chrome.PAIR_DIM,
                            bold=bool(v), dim=not v)
            try:
                win.addstr(top + r, left + c * 6, text.center(5), a)
            except curses.error:
                pass


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
