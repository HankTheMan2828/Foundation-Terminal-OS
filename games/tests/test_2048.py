import random

from foundation_arcade import engine
from foundation_arcade.game2048 import Game2048, _compress_merge


def test_compress_merge_slides_and_merges_once_per_pair():
    line, gained = _compress_merge([2, 2, 2, 0])
    assert line == [4, 2, 0, 0]
    assert gained == 4


def test_compress_merge_no_merge_beyond_adjacent():
    line, gained = _compress_merge([2, 0, 2, 2])
    assert line == [4, 2, 0, 0]
    assert gained == 4


def test_new_game_has_two_tiles():
    game = Game2048(rng=random.Random(1))
    nonzero = [v for row in game.board for v in row if v]
    assert len(nonzero) == 2
    assert all(v in (2, 4) for v in nonzero)


def test_move_left_merges_row():
    game = Game2048(rng=random.Random(1))
    game.board = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    changed = game.move(engine.DIR_LEFT)
    assert changed
    assert game.board[0][0] == 4
    assert game.score == 4


def test_move_returns_false_when_board_unchanged():
    game = Game2048(rng=random.Random(1))
    game.board = [[2, 4, 8, 16], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    assert game.move(engine.DIR_LEFT) is False


def test_move_right_and_down_reduce_correctly():
    game = Game2048(rng=random.Random(1))
    game.board = [[2, 2, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    game.move(engine.DIR_RIGHT)
    assert game.board[0][-1] == 4


def test_is_game_over_detects_no_moves_left():
    game = Game2048(rng=random.Random(1))
    game.board = [
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2],
    ]
    assert game.is_game_over()


def test_has_won_at_2048_tile():
    game = Game2048(rng=random.Random(1))
    game.board[0][0] = 2048
    assert game.has_won()
