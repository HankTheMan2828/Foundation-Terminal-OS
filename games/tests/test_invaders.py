import random

from foundation_arcade.invaders import InvadersGame


def test_fire_then_second_fire_is_blocked_until_bullet_clears():
    game = InvadersGame(rng=random.Random(1))
    assert game.fire() is True
    assert game.fire() is False   # only one player bullet in flight at a time


def test_bullet_hits_alien_and_scores():
    game = InvadersGame(width=10, height=10, rng=random.Random(1))
    game.aliens = {(3, 5)}
    game.player_bullet = (4, 5)
    game.step()
    assert (3, 5) not in game.aliens
    assert game.score == 10
    assert game.player_bullet is None


def test_win_when_all_aliens_cleared():
    game = InvadersGame(width=10, height=10, rng=random.Random(1))
    game.aliens = set()
    game.step()
    assert game.won


def test_alien_reaching_bottom_ends_game():
    game = InvadersGame(width=10, height=6, rng=random.Random(1))
    game.aliens = {(4, 2)}
    game.march_aliens()
    assert game.game_over


def test_alien_bullet_hits_player_and_costs_a_life():
    game = InvadersGame(width=10, height=10, rng=random.Random(1))
    game.player_col = 5
    game.alien_bullets = [(8, 5)]
    lives_before = game.lives
    game.step()
    assert game.lives == lives_before - 1


def test_player_dies_when_lives_run_out():
    game = InvadersGame(width=10, height=10, rng=random.Random(1))
    game.lives = 1
    game.player_col = 5
    game.alien_bullets = [(8, 5)]
    game.step()
    assert game.game_over
