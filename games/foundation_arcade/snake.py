"""Snake — retires nsnake."""
from __future__ import annotations

import curses
import random
from collections import deque

from . import chrome, engine, labels, scores

STEP_MS = 120
BOARD_W, BOARD_H = 34, 18


class SnakeGame:
    """Pure logic: no curses. `step()` advances one tick; `set_direction()`
    queues the next move and ignores an immediate reversal (can't turn the
    snake back into itself)."""

    def __init__(self, width: int = BOARD_W, height: int = BOARD_H, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        cy, cx = height // 2, width // 2
        self.snake = deque([(cy, cx), (cy, cx - 1), (cy, cx - 2)])
        self.direction = engine.DIR_RIGHT
        self._pending = self.direction
        self.score = 0
        self.game_over = False
        self.food = self._place_food()

    def _place_food(self) -> tuple[int, int]:
        occupied = set(self.snake)
        free = [(r, c) for r in range(self.height) for c in range(self.width)
                if (r, c) not in occupied]
        return self.rng.choice(free) if free else (0, 0)

    def set_direction(self, d: tuple[int, int]) -> None:
        if d[0] == -self.direction[0] and d[1] == -self.direction[1]:
            return  # no direct reversal
        self._pending = d

    def step(self) -> None:
        if self.game_over:
            return
        self.direction = self._pending
        head_r, head_c = self.snake[0]
        dr, dc = self.direction
        new_head = (head_r + dr, head_c + dc)
        if not (0 <= new_head[0] < self.height and 0 <= new_head[1] < self.width):
            self.game_over = True
            return
        grows = new_head == self.food
        body = self.snake if grows else deque(list(self.snake)[:-1])
        if new_head in body:
            self.game_over = True
            return
        self.snake.appendleft(new_head)
        if grows:
            self.score += 1
            self.food = self._place_food()
        else:
            self.snake.pop()


def run(win) -> int:
    """Curses screen. Returns the final score."""
    h, w = win.getmaxyx()
    game = SnakeGame(width=min(BOARD_W, w - 4), height=min(BOARD_H, h - 8))
    path = scores.scores_path()
    best = scores.best_score(path, labels.GAME_SNAKE)
    clock = engine.Clock()
    acc = engine.StepAccumulator(STEP_MS)
    win.nodelay(True)
    win.timeout(30)
    paused = False

    while True:
        top, left = chrome.draw_chrome(win, labels.GAME_SNAKE)
        top, left = chrome.draw_playfield(win, top, left, game.height, game.width * 2)
        _draw_board(win, top, left, game)
        status = labels.PAUSED if paused else (
            f"{labels.SCORE} {game.score}   {labels.BEST} {max(best, game.score)}")
        chrome.draw_statusbar(win, status)
        win.noutrefresh()
        curses.doupdate()

        key = win.getch()
        if key in engine.KEYS_QUIT:
            break
        if key in engine.KEYS_PAUSE:
            paused = not paused
        d = engine.direction_for(key)
        if d is not None:
            game.set_direction(d)

        dt = clock.elapsed_ms()
        if not paused and not game.game_over:
            for _ in range(acc.advance(dt)):
                game.step()
        elif game.game_over:
            scores.record_score(path, labels.GAME_SNAKE, game.score)
            _flash_end(win, labels.GAME_OVER)
            win.nodelay(False)
            win.getch()
            break

    return game.score


def _draw_board(win, top: int, left: int, game: SnakeGame) -> None:
    body = chrome.attr(chrome.PAIR_NORMAL)
    head = chrome.attr(chrome.PAIR_HILITE, bold=True)
    food = chrome.attr(chrome.PAIR_WARN, bold=True)
    for i, (r, c) in enumerate(game.snake):
        try:
            win.addch(top + r, left + c * 2, ord("@") if i == 0 else ord("o"),
                      head if i == 0 else body)
        except curses.error:
            pass
    fr, fc = game.food
    try:
        win.addch(top + fr, left + fc * 2, ord("*"), food)
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
