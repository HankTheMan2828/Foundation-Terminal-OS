#!/usr/bin/env python3
"""Stitch the preview PNGs into one labeled contact sheet."""
import pathlib
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).parent / "preview"
ORDER = [
    ("01_home", "HOME HUB"),
    ("02_programs", "PROGRAMS"),
    ("03_recreation", "RECREATION"),
    ("04_functions", "FUNCTIONS"),
    ("05_brightness", "BRIGHTNESS (submenu)"),
    ("06_settings", "CONFIGURATION (no Frank)"),
    ("07_logs", "LOGS"),
    ("08_ledger", "OVERSEER LEDGER (empty)"),
    ("13_ledger_populated", "OVERSEER LEDGER (populated)"),
    ("09_notes", "PERSONAL FILE"),
    ("10_assistant", "ASSISTANT (offline)"),
    ("11_power", "POWER"),
    ("12_lockout", "FRANK LOCKOUT (root)"),
]


def main():
    cols, tw, th, lab, pad = 3, 520, 360, 30, 14
    imgs = [(Image.open(OUT / f"{n}.png"), lb) for n, lb in ORDER
            if (OUT / f"{n}.png").exists()]
    rows = (len(imgs) + cols - 1) // cols
    W = cols * (tw + pad) + pad
    H = rows * (th + lab + pad) + pad
    sheet = Image.new("RGB", (W, H), (6, 5, 4))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 20)
    for i, (im, lb) in enumerate(imgs):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + lab + pad)
        d.text((x + 2, y), lb, font=f, fill=(255, 176, 0))
        sheet.paste(im.resize((tw, th)), (x, y + lab))
    sheet.save(OUT / "00_contact_sheet.png")
    print("wrote 00_contact_sheet")


if __name__ == "__main__":
    main()
