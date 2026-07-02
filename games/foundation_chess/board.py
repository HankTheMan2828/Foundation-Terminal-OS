"""Chess rules engine — pure logic, no curses (BUILD-QUEUE §5 item 2).

The whole point of this module is correctness: full legal move generation
(castling, en passant, promotion, pins, check evasion), so it's kept a plain
library with zero curses so it can be unit-tested headlessly and validated
with perft node counts (see tests/test_chess.py).

Board orientation: `grid[r][c]` with r=0 the top of the screen (rank 8, Black's
back rank) and r=7 the bottom (rank 1, White's back rank). White is uppercase,
Black lowercase, '.' is empty. White moves up the board (row index decreasing).
"""
from __future__ import annotations

from dataclasses import dataclass

WHITE, BLACK = "w", "b"

# Piece letters are the classic FEN set; case encodes color.
WHITE_PIECES = set("PNBRQK")
BLACK_PIECES = set("pnbrqk")
EMPTY = "."

# Ray/step tables shared by generation and attack detection.
_KNIGHT = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
_KING = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_BISHOP = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
_ROOK = [(-1, 0), (1, 0), (0, -1), (0, 1)]

_FILES = "abcdefgh"


def color_of(piece: str) -> str | None:
    if piece in WHITE_PIECES:
        return WHITE
    if piece in BLACK_PIECES:
        return BLACK
    return None


def on_board(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


def square_name(sq: tuple[int, int]) -> str:
    r, c = sq
    return f"{_FILES[c]}{8 - r}"


def parse_square(name: str) -> tuple[int, int]:
    c = _FILES.index(name[0])
    r = 8 - int(name[1])
    return (r, c)


@dataclass(frozen=True)
class Move:
    """A move is source square, destination square, and an optional promotion
    piece (uppercase letter — color is applied on the board). Castling, double
    pushes, and en passant carry no extra flag: `make_move` re-derives them
    from the piece and board state, which keeps a Move trivially comparable."""

    frm: tuple[int, int]
    to: tuple[int, int]
    promo: str | None = None

    def uci(self) -> str:
        s = square_name(self.frm) + square_name(self.to)
        return s + self.promo.lower() if self.promo else s


class Board:
    __slots__ = ("grid", "turn", "castling", "ep", "halfmove", "fullmove")

    def __init__(self, grid, turn, castling, ep, halfmove, fullmove):
        self.grid = grid
        self.turn = turn
        self.castling = castling  # subset of {"K","Q","k","q"}
        self.ep = ep              # en-passant target square (r,c) or None
        self.halfmove = halfmove  # halfmove clock for the 50-move rule
        self.fullmove = fullmove

    # -- construction --
    @classmethod
    def initial(cls) -> "Board":
        return cls.from_fen(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

    @classmethod
    def from_fen(cls, fen: str) -> "Board":
        parts = fen.split()
        rows = parts[0].split("/")
        grid = []
        for row in rows:
            cells = []
            for ch in row:
                if ch.isdigit():
                    cells.extend(EMPTY * int(ch))
                else:
                    cells.append(ch)
            grid.append(cells)
        turn = parts[1] if len(parts) > 1 else "w"
        castling = set(c for c in (parts[2] if len(parts) > 2 else "-") if c in "KQkq")
        ep = None
        if len(parts) > 3 and parts[3] != "-":
            ep = parse_square(parts[3])
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1
        return cls(grid, turn, castling, ep, halfmove, fullmove)

    def to_fen(self) -> str:
        rows = []
        for r in range(8):
            run = 0
            out = ""
            for c in range(8):
                p = self.grid[r][c]
                if p == EMPTY:
                    run += 1
                else:
                    if run:
                        out += str(run)
                        run = 0
                    out += p
            if run:
                out += str(run)
            rows.append(out)
        placement = "/".join(rows)
        castling = "".join(k for k in "KQkq" if k in self.castling) or "-"
        ep = square_name(self.ep) if self.ep else "-"
        return f"{placement} {self.turn} {castling} {ep} {self.halfmove} {self.fullmove}"

    def copy(self) -> "Board":
        return Board([row[:] for row in self.grid], self.turn, set(self.castling),
                     self.ep, self.halfmove, self.fullmove)

    # -- queries --
    def piece_at(self, r: int, c: int) -> str:
        return self.grid[r][c]

    def king_square(self, side: str) -> tuple[int, int] | None:
        king = "K" if side == WHITE else "k"
        for r in range(8):
            for c in range(8):
                if self.grid[r][c] == king:
                    return (r, c)
        return None

    def is_attacked(self, r: int, c: int, by: str) -> bool:
        """Is square (r,c) attacked by any piece of color `by`? Used for check
        detection and castling — deliberately does NOT call move generation, so
        there's no mutual recursion."""
        g = self.grid
        # Pawns. A white pawn on (pr,pc) attacks (pr-1, pc±1); a black pawn
        # attacks (pr+1, pc±1). So look one rank toward the attacker's home.
        pr = r + 1 if by == WHITE else r - 1
        pawn = "P" if by == WHITE else "p"
        for pc in (c - 1, c + 1):
            if on_board(pr, pc) and g[pr][pc] == pawn:
                return True
        # Knights.
        knight = "N" if by == WHITE else "n"
        for dr, dc in _KNIGHT:
            rr, cc = r + dr, c + dc
            if on_board(rr, cc) and g[rr][cc] == knight:
                return True
        # King.
        king = "K" if by == WHITE else "k"
        for dr, dc in _KING:
            rr, cc = r + dr, c + dc
            if on_board(rr, cc) and g[rr][cc] == king:
                return True
        # Sliding: bishops/queens on diagonals, rooks/queens orthogonally.
        bishoplike = ("B", "Q") if by == WHITE else ("b", "q")
        rooklike = ("R", "Q") if by == WHITE else ("r", "q")
        for dirs, targets in ((_BISHOP, bishoplike), (_ROOK, rooklike)):
            for dr, dc in dirs:
                rr, cc = r + dr, c + dc
                while on_board(rr, cc):
                    p = g[rr][cc]
                    if p != EMPTY:
                        if p in targets:
                            return True
                        break
                    rr += dr
                    cc += dc
        return False

    def in_check(self, side: str) -> bool:
        ks = self.king_square(side)
        if ks is None:
            return False
        return self.is_attacked(ks[0], ks[1], BLACK if side == WHITE else WHITE)


# -- move generation --------------------------------------------------------

def _pseudo_moves(board: Board, side: str) -> list[Move]:
    """All moves that respect piece movement rules and board occupancy, but
    NOT the king-safety rule (a pseudo move may leave the mover in check).
    `legal_moves` filters those out."""
    g = board.grid
    moves: list[Move] = []
    enemy = BLACK if side == WHITE else WHITE
    forward = -1 if side == WHITE else 1        # white moves up (row-)
    start_row = 6 if side == WHITE else 1
    promo_row = 0 if side == WHITE else 7

    for r in range(8):
        for c in range(8):
            p = g[r][c]
            if color_of(p) != side:
                continue
            t = p.upper()
            if t == "P":
                one = r + forward
                if on_board(one, c) and g[one][c] == EMPTY:
                    _add_pawn(moves, (r, c), (one, c), one == promo_row)
                    two = r + 2 * forward
                    if r == start_row and g[two][c] == EMPTY:
                        moves.append(Move((r, c), (two, c)))
                for dc in (-1, 1):
                    cc = c + dc
                    if not on_board(one, cc):
                        continue
                    target = g[one][cc]
                    if color_of(target) == enemy:
                        _add_pawn(moves, (r, c), (one, cc), one == promo_row)
                    elif board.ep == (one, cc):
                        moves.append(Move((r, c), (one, cc)))  # en passant
            elif t == "N":
                for dr, dc in _KNIGHT:
                    rr, cc = r + dr, c + dc
                    if on_board(rr, cc) and color_of(g[rr][cc]) != side:
                        moves.append(Move((r, c), (rr, cc)))
            elif t == "K":
                for dr, dc in _KING:
                    rr, cc = r + dr, c + dc
                    if on_board(rr, cc) and color_of(g[rr][cc]) != side:
                        moves.append(Move((r, c), (rr, cc)))
                _add_castles(board, side, (r, c), moves)
            else:  # sliding B/R/Q
                dirs = _BISHOP if t == "B" else _ROOK if t == "R" else _BISHOP + _ROOK
                for dr, dc in dirs:
                    rr, cc = r + dr, c + dc
                    while on_board(rr, cc):
                        occ = g[rr][cc]
                        if occ == EMPTY:
                            moves.append(Move((r, c), (rr, cc)))
                        else:
                            if color_of(occ) == enemy:
                                moves.append(Move((r, c), (rr, cc)))
                            break
                        rr += dr
                        cc += dc
    return moves


def _add_pawn(moves: list[Move], frm, to, is_promo: bool) -> None:
    if is_promo:
        for promo in ("Q", "R", "B", "N"):
            moves.append(Move(frm, to, promo))
    else:
        moves.append(Move(frm, to))


def _add_castles(board: Board, side: str, king_sq, moves: list[Move]) -> None:
    r, c = king_sq
    home = 7 if side == WHITE else 0
    if (r, c) != (home, 4):
        return
    enemy = BLACK if side == WHITE else WHITE
    if board.is_attacked(home, 4, enemy):
        return  # can't castle out of check
    g = board.grid
    ks_right = "K" if side == WHITE else "k"
    qs_right = "Q" if side == WHITE else "q"
    rook = "R" if side == WHITE else "r"
    # Kingside: squares f,g empty and not attacked; rook on h.
    if ks_right in board.castling and g[home][5] == EMPTY and g[home][6] == EMPTY \
            and g[home][7] == rook \
            and not board.is_attacked(home, 5, enemy) \
            and not board.is_attacked(home, 6, enemy):
        moves.append(Move((home, 4), (home, 6)))
    # Queenside: b,c,d empty (b need not be un-attacked), c,d not attacked; rook on a.
    if qs_right in board.castling and g[home][1] == EMPTY and g[home][2] == EMPTY \
            and g[home][3] == EMPTY and g[home][0] == rook \
            and not board.is_attacked(home, 3, enemy) \
            and not board.is_attacked(home, 2, enemy):
        moves.append(Move((home, 4), (home, 2)))


def legal_moves(board: Board) -> list[Move]:
    """Pseudo moves filtered to those that don't leave the mover's king in
    check. Castling's pass-through squares are already vetted in generation."""
    side = board.turn
    out = []
    for mv in _pseudo_moves(board, side):
        nxt = make_move(board, mv)
        if not nxt.in_check(side):
            out.append(mv)
    return out


def make_move(board: Board, mv: Move) -> Board:
    """Apply `mv` and return a new Board (the caller's is untouched). Trusts
    that `mv` is at least pseudo-legal for the side to move."""
    nb = board.copy()
    g = nb.grid
    side = board.turn
    fr, fc = mv.frm
    tr, tc = mv.to
    piece = g[fr][fc]
    t = piece.upper()
    captured = g[tr][tc]
    is_pawn = t == "P"

    # En passant capture: pawn moves diagonally onto the (empty) ep square.
    ep_capture = is_pawn and (tr, tc) == board.ep and captured == EMPTY
    if ep_capture:
        g[fr][tc] = EMPTY  # the captured pawn sits beside the moving pawn

    # Move the piece (apply promotion).
    g[fr][fc] = EMPTY
    if mv.promo:
        g[tr][tc] = mv.promo if side == WHITE else mv.promo.lower()
    else:
        g[tr][tc] = piece

    # Castling: king jumps two files -> hop the matching rook over it.
    if t == "K" and abs(tc - fc) == 2:
        if tc == 6:            # kingside
            g[tr][5] = g[tr][7]
            g[tr][7] = EMPTY
        else:                  # queenside (tc == 2)
            g[tr][3] = g[tr][0]
            g[tr][0] = EMPTY

    # En-passant target: only after a double pawn push.
    nb.ep = None
    if is_pawn and abs(tr - fr) == 2:
        nb.ep = ((fr + tr) // 2, fc)

    # Castling rights: lose them if the king or a rook leaves home, or a rook
    # is captured on its home square.
    _revoke_castling(nb, piece, (fr, fc), (tr, tc))

    # 50-move clock: reset on pawn moves and captures, else increment.
    if is_pawn or captured != EMPTY or ep_capture:
        nb.halfmove = 0
    else:
        nb.halfmove = board.halfmove + 1

    nb.turn = BLACK if side == WHITE else WHITE
    if side == BLACK:
        nb.fullmove = board.fullmove + 1
    return nb


def _revoke_castling(nb: Board, piece: str, frm, to) -> None:
    if piece == "K":
        nb.castling.discard("K")
        nb.castling.discard("Q")
    elif piece == "k":
        nb.castling.discard("k")
        nb.castling.discard("q")
    # A rook leaving (or being captured on) a corner kills that side's right.
    corner = {(7, 7): "K", (7, 0): "Q", (0, 7): "k", (0, 0): "q"}
    for sq in (frm, to):
        if sq in corner:
            nb.castling.discard(corner[sq])


# -- game state -------------------------------------------------------------

NORMAL, CHECK, CHECKMATE, STALEMATE, DRAW_50, DRAW_MATERIAL = (
    "normal", "check", "checkmate", "stalemate", "draw_50", "draw_material")


def insufficient_material(board: Board) -> bool:
    """K vs K, K+minor vs K, and K+B vs K+B with same-colored bishops. Enough
    to stop the AI from 'winning' a dead position; not a full FIDE ruling."""
    minors = []
    for r in range(8):
        for c in range(8):
            p = board.grid[r][c]
            t = p.upper()
            if t in ("P", "R", "Q"):
                return False
            if t in ("N", "B"):
                minors.append((t, (r + c) % 2))
    if len(minors) <= 1:
        return True
    if len(minors) == 2 and all(m[0] == "B" for m in minors) \
            and minors[0][1] == minors[1][1]:
        return True
    return False


def status(board: Board) -> str:
    """Classify the position for the side to move."""
    moves = legal_moves(board)
    checked = board.in_check(board.turn)
    if not moves:
        return CHECKMATE if checked else STALEMATE
    if insufficient_material(board):
        return DRAW_MATERIAL
    if board.halfmove >= 100:
        return DRAW_50
    return CHECK if checked else NORMAL


def is_game_over(board: Board) -> bool:
    return status(board) in (CHECKMATE, STALEMATE, DRAW_50, DRAW_MATERIAL)


def perft(board: Board, depth: int) -> int:
    """Count leaf nodes to `depth` — the standard move-gen correctness probe."""
    if depth == 0:
        return 1
    total = 0
    for mv in legal_moves(board):
        total += perft(make_move(board, mv), depth - 1)
    return total
