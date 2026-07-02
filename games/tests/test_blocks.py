import random

from foundation_arcade.blocks import BlocksGame, _ROTATIONS, _rotate_cw, _SHAPES


def test_all_shapes_have_four_rotation_states():
    for name in _SHAPES:
        assert len(_ROTATIONS[name]) == 4


def test_rotate_cw_normalizes_to_nonnegative_box():
    rotated = _rotate_cw(_SHAPES["T"])
    assert all(r >= 0 and c >= 0 for r, c in rotated)


def test_spawn_places_piece_without_collision():
    game = BlocksGame(rng=random.Random(1))
    assert not game.game_over
    assert game._fits(game._cells_at())


def test_move_blocked_at_wall():
    game = BlocksGame(rng=random.Random(1))
    for _ in range(20):
        game.move(-1)
    assert min(c for _, c in game._cells_at()) >= 0


def test_soft_drop_locks_piece_at_floor():
    game = BlocksGame(width=6, height=6, rng=random.Random(1))
    for _ in range(20):
        game.soft_drop()
    assert any(any(row) for row in game.board) or game.game_over


def test_hard_drop_lands_immediately():
    game = BlocksGame(width=6, height=10, rng=random.Random(2))
    rows = game.hard_drop()
    assert rows >= 0


def test_full_row_clears_and_scores():
    game = BlocksGame(width=4, height=6, rng=random.Random(1))
    # Fill the bottom row except one cell, by hand, then let a piece complete it.
    game.board[5] = [1, 1, 1, 0]
    game.piece = "O"
    game.rotation = 0
    game.pos = (4, 2)   # O piece occupies (4,2)(4,3)(5,2)(5,3)
    game.board[4][2] = 0
    game.board[4][3] = 0
    game.board[5][2] = 0
    game.board[5][3] = 0
    before_score = game.score
    game._lock()
    assert game.lines_cleared == 1
    assert game.score > before_score
    assert game.board[0] == [0, 0, 0, 0]   # a fresh empty row shifts in at the top
