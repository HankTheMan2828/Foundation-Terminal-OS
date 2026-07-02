"""User-visible strings — every one lives here (matches the Hub's labels.py
convention: no literal UI strings scattered through the game modules)."""
from __future__ import annotations

CHESS_TITLE = "FOUNDATION CHESS"
CHESS_TAGLINE = "the operator vs. the machine"

# Start menu.
MENU_SIDE = "PLAY AS"
SIDE_WHITE = "WHITE (move first)"
SIDE_BLACK = "BLACK"
MENU_DIFFICULTY = "OPPONENT"
DIFF_EASY = "NOVICE"        # -> DEPTHS["EASY"]
DIFF_NORMAL = "REGULAR"     # -> DEPTHS["NORMAL"]
MENU_BEGIN = "BEGIN GAME"
MENU_HINT = "UP/DOWN or W/S select · LEFT/RIGHT change · ENTER confirm · ESC/Q quit"

# In-game.
HINT_MOVE = "arrows/hjkl move · ENTER select/move · ESC menu"
YOUR_MOVE = "YOUR MOVE"
THINKING = "opponent thinking…"
CHECK = "CHECK"
IN_CHECK = "-- CHECK --"
LAST = "LAST"

# Results.
RESULT_WIN = "YOU WIN — CHECKMATE"
RESULT_LOSS = "CHECKMATE — YOU LOSE"
RESULT_STALEMATE = "DRAW — STALEMATE"
RESULT_DRAW_50 = "DRAW — 50-MOVE RULE"
RESULT_DRAW_MATERIAL = "DRAW — INSUFFICIENT MATERIAL"
RESULT_RESIGN = "YOU RESIGNED"
PRESS_CONTINUE = "press any key to continue"

# Esc menu.
ESC_TITLE = "PAUSED"
ESC_RESUME = "RESUME"
ESC_NEWGAME = "NEW GAME"
ESC_RESIGN = "RESIGN"
ESC_QUIT = "QUIT TO RECREATION"

# Promotion picker.
PROMOTE_PROMPT = "PROMOTE TO:"
PROMOTE_Q = "QUEEN"
PROMOTE_R = "ROOK"
PROMOTE_B = "BISHOP"
PROMOTE_N = "KNIGHT"

# Per-user record line (header).
RECORD = "RECORD"
RECORD_FMT = "W {w} · L {l} · D {d}"

TOO_SMALL = "terminal too small — resize and retry"
