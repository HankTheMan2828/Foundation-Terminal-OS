"""Falling Blocks — a Tetris-like, retires vitetris."""
from __future__ import annotations

import curses
import random

from . import chrome, engine, labels, scores

BOARD_W, BOARD_H = 10, 20
BASE_STEP_MS = 600
MIN_STEP_MS = 100
LINES_PER_LEVEL = 10
LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}

# Each shape as its base rotation's occupied cells in a tight bounding box.
_SHAPES: dict[str, list[tuple[int, int]]] = {
    "I": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
    "S": [(0, 1), (0, 2), (1, 0), (1, 1)],
    "Z": [(0, 0), (0, 1), (1, 1), (1, 2)],
    "J": [(0, 0), (1, 0), (1, 1), (1, 2)],
    "L": [(0, 2), (1, 0), (1, 1), (1, 2)],
}
_SHAPE_NAMES = list(_SHAPES)


def _normalize(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return [(r - min_r, c - min_c) for r, c in cells]


def _rotate_cw(cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    max_r = max(r for r, _ in cells)
    return _normalize([(c, max_r - r) for r, c in cells])


def _rotations(name: str) -> list[list[tuple[int, int]]]:
    states = [_SHAPES[name]]
    for _ in range(3):
        states.append(_rotate_cw(states[-1]))
    return states


_ROTATIONS = {name: _rotations(name) for name in _SHAPE_NAMES}


class BlocksGame:
    """Pure logic: board, active piece, gravity ticks via step()."""

    def __init__(self, width: int = BOARD_W, height: int = BOARD_H, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        self.board = [[0] * width for _ in range(height)]
        self.score = 0
        self.lines_cleared = 0
        self.game_over = False
        self._next_type = self.rng.choice(_SHAPE_NAMES)
        self._spawn()

    @property
    def level(self) -> int:
        return 1 + self.lines_cleared // LINES_PER_LEVEL

    def _cells_at(self) -> list[tuple[int, int]]:
        pr, pc = self.pos
        return [(pr + r, pc + c) for r, c in _ROTATIONS[self.piece][self.rotation]]

    def _fits(self, cells: list[tuple[int, int]]) -> bool:
        for r, c in cells:
            if not (0 <= r < self.height and 0 <= c < self.width):
                return False
            if self.board[r][c]:
                return False
        return True

    def _spawn(self) -> None:
        self.piece = self._next_type
        self._next_type = self.rng.choice(_SHAPE_NAMES)
        self.rotation = 0
        width_span = max(c for _, c in _ROTATIONS[self.piece][0]) + 1
        self.pos = (0, (self.width - width_span) // 2)
        if not self._fits(self._cells_at()):
            self.game_over = True

    # -- player actions --
    def move(self, dc: int) -> bool:
        if self.game_over:
            return False
        pr, pc = self.pos
        cells = [(r, c + dc) for r, c in self._cells_at()]
        if self._fits(cells):
            self.pos = (pr, pc + dc)
            return True
        return False

    def rotate(self) -> bool:
        if self.game_over:
            return False
        next_rotation = (self.rotation + 1) % len(_ROTATIONS[self.piece])
        pr, pc = self.pos
        base = _ROTATIONS[self.piece][next_rotation]
        for kick in (0, -1, 1, -2, 2):
            cells = [(pr + r, pc + c + kick) for r, c in base]
            if self._fits(cells):
                self.rotation = next_rotation
                self.pos = (pr, pc + kick)
                return True
        return False

    def soft_drop(self) -> bool:
        """One row down; returns False (and locks) if it can't move."""
        if self.game_over:
            return False
        pr, pc = self.pos
        cells = [(r + 1, c) for r, c in self._cells_at()]
        if self._fits(cells):
            self.pos = (pr + 1, pc)
            return True
        self._lock()
        return False

    def hard_drop(self) -> int:
        """Drop to the floor immediately. Returns rows dropped."""
        rows = 0
        while self.soft_drop():
            rows += 1
        return rows

    def step(self) -> None:
        """Gravity tick: same as a soft drop the player didn't ask for."""
        self.soft_drop()

    def _lock(self) -> None:
        for r, c in self._cells_at():
            if 0 <= r < self.height:
                self.board[r][c] = _SHAPE_NAMES.index(self.piece) + 1
        cleared = self._clear_lines()
        if cleared:
            self.lines_cleared += cleared
            self.score += LINE_SCORES.get(cleared, cleared * 200) * self.level
        if not self.game_over:
            self._spawn()

    def _clear_lines(self) -> int:
        remaining = [row for row in self.board if not all(row)]
        cleared = self.height - len(remaining)
        if cleared:
            self.board = [[0] * self.width for _ in range(cleared)] + remaining
        return cleared


def run(win) -> int:
    game = BlocksGame()
    path = scores.scores_path()
    best = scores.best_score(path, labels.GAME_BLOCKS)
    clock = engine.Clock()
    acc = engine.StepAccumulator(BASE_STEP_MS)
    win.nodelay(True)
    win.timeout(30)
    paused = False

    while True:
        top, left = chrome.draw_chrome(win, labels.GAME_BLOCKS)
        top, left = chrome.draw_playfield(win, top, left, game.height, game.width * 2)
        _draw_board(win, top, left, game)
        status = labels.PAUSED if paused else (
            f"{labels.SCORE} {game.score}   {labels.LEVEL} {game.level}   "
            f"{labels.BEST} {max(best, game.score)}")
        chrome.draw_statusbar(win, status)
        win.noutrefresh()
        curses.doupdate()

        key = win.getch()
        if key in engine.KEYS_QUIT:
            break
        if key in engine.KEYS_PAUSE:
            paused = not paused
        elif not paused and not game.game_over:
            if key in engine.KEYS_LEFT:
                game.move(-1)
            elif key in engine.KEYS_RIGHT:
                game.move(1)
            elif key in engine.KEYS_UP:
                game.rotate()
            elif key in engine.KEYS_DOWN:
                game.soft_drop()
            elif key in engine.KEYS_ACTION:
                game.hard_drop()

        acc.set_step_ms(max(MIN_STEP_MS, BASE_STEP_MS - (game.level - 1) * 40))
        dt = clock.elapsed_ms()
        if not paused and not game.game_over:
            for _ in range(acc.advance(dt)):
                game.step()
        if game.game_over:
            scores.record_score(path, labels.GAME_BLOCKS, game.score)
            _flash_end(win, labels.GAME_OVER)
            win.nodelay(False)
            win.getch()
            break

    return game.score


def _draw_board(win, top: int, left: int, game: BlocksGame) -> None:
    for r in range(game.height):
        for c in range(game.width):
            v = game.board[r][c]
            if v:
                _cell(win, top + r, left + c * 2, v)
    if not game.game_over:
        for r, c in game._cells_at():
            if r >= 0:
                _cell(win, top + r, left + c * 2, _SHAPE_NAMES.index(game.piece) + 1)


def _cell(win, y: int, x: int, color_id: int) -> None:
    # Six visually distinct pairs for the seven tetrominoes (was four, two of
    # which — NORMAL and ACCENT — collapsed to the same yellow after the palette
    # unification, so pieces shared a color).
    pairs = (chrome.PAIR_NORMAL, chrome.PAIR_AMBER, chrome.PAIR_COOL,
             chrome.PAIR_BRIGHT, chrome.PAIR_WARN, chrome.PAIR_HILITE)
    a = chrome.attr(pairs[color_id % len(pairs)], bold=True)
    try:
        win.addstr(y, x, "[]", a)
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
