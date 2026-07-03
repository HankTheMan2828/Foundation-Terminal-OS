"""Invaders — retires ninvaders."""
from __future__ import annotations

import curses
import random

from . import chrome, engine, labels, scores

WIDTH, HEIGHT = 30, 18
ALIEN_COLS, ALIEN_ROWS = 8, 4
ALIEN_STEP_MS = 500
ALIEN_STEP_MIN_MS = 120
BULLET_STEP_MS = 60
ALIEN_FIRE_CHANCE = 0.02
STARTING_LIVES = 3


class InvadersGame:
    """Pure logic: player, one player bullet at a time, an alien grid that
    marches side to side and drops a row at each wall, alien bullets."""

    def __init__(self, width: int = WIDTH, height: int = HEIGHT, rng=None):
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        self.player_col = width // 2
        self.player_bullet: tuple[int, int] | None = None      # (row, col)
        self.alien_bullets: list[tuple[int, int]] = []
        self.aliens = {(r, c) for r in range(ALIEN_ROWS) for c in range(ALIEN_COLS)}
        self.alien_dir = 1
        self.lives = STARTING_LIVES
        self.score = 0
        self.game_over = False
        self.won = False

    # -- player actions --
    def move_player(self, dc: int) -> None:
        self.player_col = max(0, min(self.width - 1, self.player_col + dc))

    def fire(self) -> bool:
        if self.player_bullet is not None:
            return False
        self.player_bullet = (self.height - 2, self.player_col)
        return True

    # -- world step (called on a fixed tick) --
    def step(self) -> None:
        if self.game_over or self.won:
            return
        self._move_bullets()
        self._check_bullet_hits()
        if not self.aliens:
            self.won = True

    def march_aliens(self) -> None:
        if self.game_over or self.won or not self.aliens:
            return
        cols = [c for _, c in self.aliens]
        min_c, max_c = min(cols), max(cols)
        would_hit_wall = (self.alien_dir > 0 and max_c + self.alien_dir >= self.width) or \
                         (self.alien_dir < 0 and min_c + self.alien_dir < 0)
        if would_hit_wall:
            self.alien_dir *= -1
            self.aliens = {(r + 1, c) for r, c in self.aliens}
        else:
            self.aliens = {(r, c + self.alien_dir) for r, c in self.aliens}
        for r, _ in self.aliens:
            if r >= self.height - 2:
                self.game_over = True
        self._maybe_alien_fire()

    def _maybe_alien_fire(self) -> None:
        if not self.aliens or self.rng.random() > ALIEN_FIRE_CHANCE:
            return
        r, c = self.rng.choice(list(self.aliens))
        self.alien_bullets.append((r, c))

    def _move_bullets(self) -> None:
        if self.player_bullet is not None:
            r, c = self.player_bullet
            r -= 1
            self.player_bullet = (r, c) if r >= 0 else None
        moved = []
        for r, c in self.alien_bullets:
            r += 1
            if r < self.height:
                moved.append((r, c))
        self.alien_bullets = moved

    def _check_bullet_hits(self) -> None:
        if self.player_bullet is not None and self.player_bullet in self.aliens:
            self.aliens.discard(self.player_bullet)
            self.score += 10
            self.player_bullet = None
        remaining = []
        for r, c in self.alien_bullets:
            if r >= self.height - 1 and c == self.player_col:
                self.lives -= 1
                if self.lives <= 0:
                    self.game_over = True
                continue
            remaining.append((r, c))
        self.alien_bullets = remaining


def run(win) -> int:
    game = InvadersGame()
    path = scores.scores_path()
    best = scores.best_score(path, labels.GAME_INVADERS)
    clock = engine.Clock()
    bullet_acc = engine.StepAccumulator(BULLET_STEP_MS)
    alien_acc = engine.StepAccumulator(ALIEN_STEP_MS)
    win.nodelay(True)
    win.timeout(30)
    paused = False

    while True:
        top, left = chrome.draw_chrome(win, labels.GAME_INVADERS)
        top, left = chrome.draw_playfield(win, top, left, game.height, game.width * 2)
        _draw(win, top, left, game)
        status = labels.PAUSED if paused else (
            f"{labels.SCORE} {game.score}   {labels.LIVES} {game.lives}   "
            f"{labels.BEST} {max(best, game.score)}")
        chrome.draw_statusbar(win, status)
        win.noutrefresh()
        curses.doupdate()

        key = win.getch()
        if key in engine.KEYS_QUIT:
            break
        if key in engine.KEYS_PAUSE:
            paused = not paused
        elif not paused and not game.game_over and not game.won:
            if key in engine.KEYS_LEFT:
                game.move_player(-1)
            elif key in engine.KEYS_RIGHT:
                game.move_player(1)
            elif key in engine.KEYS_ACTION:
                game.fire()

        remaining_aliens = len(game.aliens) or 1
        alien_acc.set_step_ms(max(ALIEN_STEP_MIN_MS,
                                   ALIEN_STEP_MS * remaining_aliens // (ALIEN_COLS * ALIEN_ROWS)))
        dt = clock.elapsed_ms()
        if not paused and not game.game_over and not game.won:
            for _ in range(bullet_acc.advance(dt)):
                game.step()
            for _ in range(alien_acc.advance(dt)):
                game.march_aliens()

        if game.game_over or game.won:
            scores.record_score(path, labels.GAME_INVADERS, game.score)
            _flash_end(win, labels.YOU_WIN if game.won else labels.GAME_OVER)
            win.nodelay(False)
            win.getch()
            break

    return game.score


def _draw(win, top: int, left: int, game: InvadersGame) -> None:
    alien_a = chrome.attr(chrome.PAIR_ACCENT, bold=True)
    player_a = chrome.attr(chrome.PAIR_HILITE, bold=True)
    bullet_a = chrome.attr(chrome.PAIR_WARN, bold=True)
    for r, c in game.aliens:
        try:
            win.addch(top + r, left + c * 2, ord("W"), alien_a)
        except curses.error:
            pass
    for r, c in game.alien_bullets:
        try:
            win.addch(top + r, left + c * 2, ord("!"), bullet_a)
        except curses.error:
            pass
    if game.player_bullet is not None:
        r, c = game.player_bullet
        try:
            win.addch(top + r, left + c * 2, ord("|"), bullet_a)
        except curses.error:
            pass
    try:
        win.addch(top + game.height - 1, left + game.player_col * 2, ord("A"), player_a)
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
