import random

from foundation_arcade.snake import SnakeGame


def test_snake_moves_in_starting_direction():
    game = SnakeGame(width=10, height=10, rng=random.Random(1))
    head = game.snake[0]
    game.step()
    new_head = game.snake[0]
    assert new_head == (head[0], head[1] + 1)   # DIR_RIGHT


def test_snake_cannot_reverse_directly():
    game = SnakeGame(width=10, height=10, rng=random.Random(1))
    from foundation_arcade import engine
    game.set_direction(engine.DIR_LEFT)   # opposite of current DIR_RIGHT
    game.step()
    # still moved right, not left, because the reversal was ignored
    assert game.direction == engine.DIR_RIGHT


def test_snake_dies_on_wall():
    game = SnakeGame(width=5, height=5, rng=random.Random(1))
    for _ in range(5):
        game.step()
    assert game.game_over


def test_snake_grows_and_scores_on_food():
    game = SnakeGame(width=10, height=10, rng=random.Random(1))
    length_before = len(game.snake)
    game.food = (game.snake[0][0], game.snake[0][1] + 1)  # directly ahead
    game.step()
    assert game.score == 1
    assert len(game.snake) == length_before + 1


def test_snake_dies_on_self_collision():
    game = SnakeGame(width=10, height=10, rng=random.Random(1))
    from foundation_arcade import engine
    # (4, 5) sits in the body (not the tail, which gets vacated this step),
    # so moving the head onto it must be a collision.
    game.snake.clear()
    game.snake.extend([(5, 5), (5, 6), (5, 7), (4, 5), (3, 5)])
    game.direction = engine.DIR_UP
    game._pending = engine.DIR_UP
    game.food = (0, 0)
    game.step()
    assert game.game_over
