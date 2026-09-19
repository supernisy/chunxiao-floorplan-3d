"""按 PDF 点坐标裁图放大，便于人眼核对图例/构造做法。

用法: python pipeline/crop_pt.py name x0 y0 x1 y1 [zoom]
页面 1191x842 pt；户型墙体包络 x∈[128,809], y∈[73,775]（见 scale.json）。
"""
import os, sys
import pymupdf as fitz

SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data")

if len(sys.argv) < 6:
    print(__doc__)
    sys.exit(1)
name = sys.argv[1]
x0, y0, x1, y1 = (float(v) for v in sys.argv[2:6])
zoom = float(sys.argv[6]) if len(sys.argv) > 6 else 3.0

doc = fitz.open(SRC)
page = doc[0]
r = fitz.Rect(x0, y0, x1, y1)
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r)
out_path = os.path.join(OUT, f"crop_{name}.png")
pix.save(out_path)
print(f"SAVED {out_path} {pix.width}x{pix.height}  pt=({x0},{y0})-({x1},{y1}) zoom={zoom}")
