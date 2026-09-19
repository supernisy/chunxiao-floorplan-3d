"""Render high-zoom clips of the dimension bars so the dimension text can be
read visually (the PDF stores text as vector outlines, not extractable glyphs).
"""
import os, fitz
SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data")
doc = fitz.open(SRC)
page = doc[0]

# Clips in PDF points (page rect 0,0 -> 1191,842)
clips = {
    "top_dims":    (0,    0,   1191, 130),
    "right_dims":  (1050, 0,   1191, 842),
    "bottom_dims": (0,   720,  1191, 842),
    "left_dims":   (0,     0,   120,  842),
}
zoom = 4
for name, (x0,y0,x1,y1) in clips.items():
    r = fitz.Rect(x0,y0,x1,y1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom,zoom), clip=r)
    out_path = os.path.join(OUT, f"clip_{name}.png")
    pix.save(out_path)
    print(f"SAVED {out_path} {pix.width}x{pix.height}")
print("CROP_DONE")
