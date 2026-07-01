"""Shared CRT renderer for the preview harness.

Turns a terminal character grid (captured from the real app via pyte) into an
amber-phosphor PNG: scanlines, glow frame, and a highlight bar on the selected
menu row. The outer box + interior rule use curses ACS glyphs, which pyte hands
back as raw DEC letters (l q k x m j …); we skip those and draw the frame
ourselves so borders come out clean.
"""
from __future__ import annotations

import pathlib
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 96, 30
_FONTDIR = "/usr/share/fonts/truetype/dejavu"
FONT = ImageFont.truetype(f"{_FONTDIR}/DejaVuSansMono.ttf", 20)
FONT_B = ImageFont.truetype(f"{_FONTDIR}/DejaVuSansMono-Bold.ttf", 20)
CW = FONT.getlength("M")
CH = 26
PAD = 24

AMBER = (255, 176, 0)
AMBER_DIM = (150, 100, 0)
RED = (255, 70, 55)
BG = (10, 8, 6)
BLACK = (8, 6, 4)


def _is_rule_row(row: str) -> bool:
    return row.count("q") > COLS * 0.5      # ACS horizontal rule


def render(grid, path, *, fg=AMBER, frame=AMBER):
    W = int(CW * COLS + PAD * 2)
    H = int(CH * ROWS + PAD * 2)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    sel = next((i for i, r in enumerate(grid) if "▶" in r), None)  # ▶
    for y, row in enumerate(grid):
        py = PAD + y * CH
        if y == 0 or y == ROWS - 1:          # top/bottom ACS border row
            continue
        if _is_rule_row(row):                # interior rule -> dim line
            yy = py + CH // 2
            d.line([(PAD, yy), (W - PAD, yy)], fill=AMBER_DIM, width=2)
            continue
        if y == sel:
            d.rectangle([PAD - 6, py - 2, W - PAD + 6, py + CH - 2], fill=fg)
        for x, ch in enumerate(row):
            if ch == " " or x == 0 or x == COLS - 1:   # skip vertical border
                continue
            d.text((PAD + x * CW, py), ch,
                   font=(FONT_B if y == sel else FONT),
                   fill=(BLACK if y == sel else fg))
    d.rectangle([PAD - 8, PAD - 6, W - PAD + 8, H - PAD + 4], outline=frame, width=2)
    # scanlines + faint outer glow
    scan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scan)
    for yy in range(0, H, 3):
        sd.line([(0, yy), (W, yy)], fill=(0, 0, 0, 46))
    img = Image.alpha_composite(img.convert("RGBA"), scan).convert("RGB")
    ImageDraw.Draw(img).rectangle([4, 4, W - 5, H - 5],
                                  outline=(70, 40, 0), width=3)
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
