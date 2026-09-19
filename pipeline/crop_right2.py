import os, fitz
SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "clip_right2.png")
doc = fitz.open(SRC)
page = doc[0]
r = fitz.Rect(980, 0, 1191, 842)
pix = page.get_pixmap(matrix=fitz.Matrix(4,4), clip=r)
pix.save(OUT)
print(f"SAVED {OUT} {pix.width}x{pix.height}")
