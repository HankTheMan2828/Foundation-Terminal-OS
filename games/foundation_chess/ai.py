"""The built-in opponent — negamax with alpha-beta over a material +
piece-square evaluation (BUILD-QUEUE §5 item 2: "minimax + a small eval is
fine; it's a terminal, not a rating ladder").

Kept curses-free and deterministic-given-an-rng so it's unit-testable: a
mate-in-one position must always be found (see tests/test_chess.py). Depth is
the difficulty knob and the portability lever — shallow search on weak hardware
(GLOBAL CONSTRAINTS: eventually a Pocket8086-tier box) still plays a legal,
non-suicidal game.
"""
from __future__ import annotations

import random

from . import board as B

# Centipawn material. King is huge but finite so the eval stays an int.
VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}

MATE = 1_000_000  # score for being checkmated, offset by ply so nearer mates win

# Difficulty -> search depth. EASY still sees one-move tactics; NORMAL sees a
# short combination. Deeper than this gets slow in pure Python and buys little
# against a casual operator, so it's not offered.
DEPTHS = {"EASY": 2, "NORMAL": 3}

# Piece-square tables, written rank-8-first (index 0 = a8) so they line up with
# this engine's board orientation (grid row 0 = rank 8). A White piece on
# grid[r][c] reads PST[r*8+c]; a Black piece reads the vertically-mirrored
# square PST[(7-r)*8+c]. Values are the well-worn Michniewski simplified set.
_PST = {
    "P": [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    "N": [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    "B": [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    "R": [
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ],
    "Q": [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    "K": [
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ],
}


def evaluate(board: B.Board) -> int:
    """Static score in centipawns, positive = good for White."""
    score = 0
    for r in range(8):
        for c in range(8):
            p = board.grid[r][c]
            if p == B.EMPTY:
                continue
            t = p.upper()
            if p in B.WHITE_PIECES:
                score += VALUE[t] + _PST[t][r * 8 + c]
            else:
                score -= VALUE[t] + _PST[t][(7 - r) * 8 + c]
    return score


def _order(board: B.Board, moves):
    """Search captures first (MVV-LVA-ish) so alpha-beta prunes hard."""
    def key(mv):
        victim = board.grid[mv.to[0]][mv.to[1]]
        if victim == B.EMPTY:
            return 0
        attacker = board.grid[mv.frm[0]][mv.frm[1]]
        return 10 * VALUE[victim.upper()] - VALUE[attacker.upper()]
    return sorted(moves, key=key, reverse=True)


def _negamax(board: B.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
    """Score from the side-to-move's perspective."""
    moves = B.legal_moves(board)
    if not moves:
        # No legal moves: checkmate (bad) or stalemate (drawn). Offset by ply so
        # the search prefers to deliver mate sooner and postpone being mated.
        return -(MATE - ply) if board.in_check(board.turn) else 0
    if depth == 0:
        sign = 1 if board.turn == B.WHITE else -1
        return sign * evaluate(board)
    best = -MATE * 2
    for mv in _order(board, moves):
        score = -_negamax(B.make_move(board, mv), depth - 1, -beta, -alpha, ply + 1)
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def best_move(board: B.Board, depth: int = 3, rng: random.Random | None = None):
    """Pick a move for the side to move. Among moves that tie for the best
    score, one is chosen at random (via `rng`) so the opponent isn't perfectly
    repetitive. Returns None if there are no legal moves."""
    rng = rng or random.Random()
    moves = B.legal_moves(board)
    if not moves:
        return None
    best_score = -MATE * 2
    best_moves: list = []
    for mv in _order(board, moves):
        score = -_negamax(B.make_move(board, mv), depth - 1, -MATE * 2, MATE * 2, 1)
        if score > best_score:
            best_score = score
            best_moves = [mv]
        elif score == best_score:
            best_moves.append(mv)
    return rng.choice(best_moves)
