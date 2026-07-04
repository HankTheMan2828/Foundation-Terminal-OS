"""Foundation Chess — rules engine, AI, and system-wide record.

The engine is validated the way chess move generators always are: perft node
counts against the standard reference positions. If castling, en passant,
promotion, pins, or check evasion were wrong, these totals would drift, so they
double as the regression guard for the whole rules layer.
"""
import random

from foundation_chess import ai, stats
from foundation_chess import board as b


# -- perft: the gold-standard move-gen correctness probe ---------------------

def test_perft_startpos():
    B = b.Board.initial()
    assert b.perft(B, 1) == 20
    assert b.perft(B, 2) == 400
    assert b.perft(B, 3) == 8902


def test_perft_kiwipete():
    # Castling + en passant + pins all exercised in one position.
    K = b.Board.from_fen(
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
    assert b.perft(K, 1) == 48
    assert b.perft(K, 2) == 2039


def test_perft_position3_promotions():
    P = b.Board.from_fen("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
    assert b.perft(P, 1) == 14
    assert b.perft(P, 3) == 2812


def test_fen_roundtrips():
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert b.Board.from_fen(fen).to_fen() == fen


# -- special moves -----------------------------------------------------------

def _ucis(board):
    return {m.uci() for m in b.legal_moves(board)}


def test_castling_both_sides_available():
    B = b.Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    moves = _ucis(B)
    assert "e1g1" in moves      # kingside
    assert "e1c1" in moves      # queenside


def test_cannot_castle_through_attacked_square():
    # Black rook on g8 rakes the g-file, so g1 (the kingside landing square) is
    # attacked: kingside is illegal, queenside still fine.
    B = b.Board.from_fen("r3k1r1/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    moves = _ucis(B)
    assert "e1g1" not in moves
    assert "e1c1" in moves


def test_en_passant_capture_removes_pawn():
    B = b.Board.from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert "e5d6" in _ucis(B)
    ep = next(m for m in b.legal_moves(B) if m.uci() == "e5d6")
    nb = b.make_move(B, ep)
    assert nb.piece_at(*b.parse_square("d6")) == "P"
    assert nb.piece_at(*b.parse_square("d5")) == b.EMPTY   # captured pawn gone


def test_promotion_generates_all_pieces_and_applies():
    B = b.Board.from_fen("7k/P7/8/8/8/8/8/4K3 w - - 0 1")
    promos = {m.promo for m in b.legal_moves(B) if m.frm == b.parse_square("a7")}
    assert promos == {"Q", "R", "B", "N"}
    queen = next(m for m in b.legal_moves(B)
                 if m.uci() == "a7a8q")
    nb = b.make_move(B, queen)
    assert nb.piece_at(*b.parse_square("a8")) == "Q"


def test_castling_rights_lost_after_king_moves():
    B = b.Board.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    nb = b.make_move(B, next(m for m in b.legal_moves(B) if m.uci() == "e1f1"))
    assert "K" not in nb.castling and "Q" not in nb.castling
    assert "k" in nb.castling and "q" in nb.castling   # black keeps its rights


# -- terminal states ---------------------------------------------------------

def test_checkmate_detected():
    B = b.Board.from_fen("6k1/5ppp/8/8/8/8/8/R6K w - - 0 1")
    mated = b.make_move(B, next(m for m in b.legal_moves(B) if m.uci() == "a1a8"))
    assert b.status(mated) == b.CHECKMATE
    assert b.is_game_over(mated)


def test_stalemate_detected():
    B = b.Board.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert b.status(B) == b.STALEMATE
    assert not B.in_check(b.BLACK)


def test_insufficient_material_is_a_draw():
    B = b.Board.from_fen("8/8/4k3/8/8/3K4/8/8 w - - 0 1")
    assert b.status(B) == b.DRAW_MATERIAL


def test_check_is_flagged_but_not_over():
    # White pawn on the board so this isn't an insufficient-material draw; Black
    # gives check with Bf2+.
    B = b.Board.from_fen("4k3/8/8/8/7b/8/4P3/4K3 b - - 0 1")
    nb = b.make_move(B, next(m for m in b.legal_moves(B) if m.uci() == "h4f2"))
    assert b.status(nb) == b.CHECK
    assert not b.is_game_over(nb)


# -- AI ----------------------------------------------------------------------

def test_ai_finds_mate_in_one():
    # Scholar's mate: Qf3xf7# is the only mate, so the pick is deterministic.
    B = b.Board.from_fen(
        "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 1")
    mv = ai.best_move(B, depth=2, rng=random.Random(0))
    assert mv.uci() == "f3f7"
    assert b.status(b.make_move(B, mv)) == b.CHECKMATE


def test_ai_returns_a_legal_move():
    B = b.Board.initial()
    mv = ai.best_move(B, depth=2, rng=random.Random(0))
    assert mv in b.legal_moves(B)


def test_ai_grabs_a_hanging_queen():
    # White queen d1, a free black queen on d5 down the open d-file: a one-ply
    # search must take it.
    B = b.Board.from_fen("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
    mv = ai.best_move(B, depth=1, rng=random.Random(0))
    assert mv.uci() == "d1d5"


def test_evaluate_is_symmetric_at_start():
    assert ai.evaluate(b.Board.initial()) == 0


# -- system-wide record -------------------------------------------------------

def test_record_missing_file_is_zeroed(tmp_path):
    rec = stats.load_record(tmp_path / "none.json")
    assert rec == {stats.WIN: 0, stats.LOSS: 0, stats.DRAW: 0}


def test_record_result_accumulates_and_persists(tmp_path):
    path = tmp_path / "chess.json"
    stats.record_result(path, stats.WIN)
    stats.record_result(path, stats.WIN)
    stats.record_result(path, stats.LOSS)
    assert path.exists()
    rec = stats.load_record(path)
    assert rec == {stats.WIN: 2, stats.LOSS: 1, stats.DRAW: 0}


def test_record_result_ignores_unknown_outcome(tmp_path):
    path = tmp_path / "chess.json"
    stats.record_result(path, "bogus")
    assert stats.load_record(path) == {stats.WIN: 0, stats.LOSS: 0, stats.DRAW: 0}


def test_record_is_one_machine_wide_tally_not_per_user(tmp_path):
    # Whoever is playing, wins/losses/draws land in the same file — there is
    # no per-user split, matching the arcade high-score board.
    path = stats.stats_path(root=tmp_path)
    assert path == tmp_path / "chess.json"
    stats.record_result(path, stats.WIN)
    stats.record_result(path, stats.LOSS)
    assert stats.load_record(path) == {stats.WIN: 1, stats.LOSS: 1, stats.DRAW: 0}
