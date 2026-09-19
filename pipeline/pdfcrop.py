"""pdfcrop.py — 按米制矩形裁 PDF 原图（带 0.5m 网格与坐标标注）。

用法: python pipeline/pdfcrop.py out.png mx0 my0 mx1 my1 [zoom]
"""
import os, sys
import numpy as np, cv2, fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M = 45.36
PP = 200.0

out = sys.argv[1]
mx0, my0, mx1, my1 = (float(v) for v in sys.argv[2:6])
zoom = float(sys.argv[6]) if len(sys.argv) > 6 else 2.6

doc = fitz.open(PDF)
pix = doc[0].get_pixmap(matrix=fitz.Matrix(PP / PT_PER_M, PP / PT_PER_M),
                        colorspace=fitz.csRGB, alpha=False)
arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
H, W = img.shape[:2]
img = cv2.copyMakeBorder(img, 0, 4, 0, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))

x0, y0 = int(mx0 * PP), int(my0 * PP)
x1, y1 = int(mx1 * PP), int(my1 * PP)
x0, y0 = max(0, x0), max(0, y0)
x1, y1 = min(W, x1), min(H, y1)
c = img[y0:y1, x0:x1].copy()
c = cv2.resize(c, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_AREA)
sc = zoom * PP                                   # px per meter in output

# 网格（0.5 m）
gx = (int(mx0 * 2) / 2.0)
while gx <= mx1 + 1e-9:
    px = int(round((gx - mx0) * sc))
    if 0 <= px < c.shape[1]:
        cv2.line(c, (px, 0), (px, c.shape[0]), (200, 200, 200), 1)
        cv2.putText(c, f"{gx:g}", (px + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (180, 0, 0), 1)
    gx += 0.5
gy = (int(my0 * 2) / 2.0)
while gy <= my1 + 1e-9:
    py = int(round((gy - my0) * sc))
    if 0 <= py < c.shape[0]:
        cv2.line(c, (0, py), (c.shape[1], py), (200, 200, 200), 1)
        cv2.putText(c, f"{gy:g}", (2, py + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (180, 0, 0), 1)
    gy += 0.5

cv2.imwrite(out, c)
print("写", out, c.shape, "px/m=", sc)
