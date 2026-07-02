import random

from foundation_arcade.sudoku import (
    N, SudokuGame, generate_puzzle, generate_solution, is_complete,
    is_valid_placement,
)


def test_generated_solution_is_a_valid_full_grid():
    solution = generate_solution(random.Random(1))
    assert is_complete(solution)
    for row in solution:
        assert sorted(row) == list(range(1, N + 1))


def test_generate_puzzle_is_subset_of_its_solution():
    puzzle, solution = generate_puzzle(random.Random(1), clues=30)
    for r in range(N):
        for c in range(N):
            if puzzle[r][c]:
                assert puzzle[r][c] == solution[r][c]
    clues = sum(1 for row in puzzle for v in row if v)
    assert clues == 30


def test_is_valid_placement_catches_row_conflict():
    board = [[0] * N for _ in range(N)]
    board[0][0] = 5
    assert not is_valid_placement(board, 0, 3, 5)


def test_is_valid_placement_catches_box_conflict():
    board = [[0] * N for _ in range(N)]
    board[0][0] = 7
    assert not is_valid_placement(board, 1, 1, 7)


def test_is_valid_placement_allows_clear():
    board = [[0] * N for _ in range(N)]
    assert is_valid_placement(board, 4, 4, 0)


def test_given_cells_cannot_be_edited():
    game = SudokuGame(rng=random.Random(1), clues=40)
    given_cell = next((r, c) for r in range(N) for c in range(N) if game.is_given(r, c))
    assert game.set_cell(*given_cell, 1) is False


def test_completing_the_solution_solves_the_game():
    game = SudokuGame(rng=random.Random(1), clues=81)   # fully given -> already solved
    assert game.solved
