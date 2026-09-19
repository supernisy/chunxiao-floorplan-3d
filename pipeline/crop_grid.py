"""按米坐标网格裁图：在图上去每 0.5m 画标尺，便于直接读出墙线的米坐标。

用法: python pipeline/crop_grid.py name x0 y0 x1 y1 [zoom]   (x/y 单位=米)
"""
import os, sys
import numpy as np
import cv2
import pymupdf as fitz

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M = 45.36

name = sys.argv[1]
mx0, my0, mx1, my1 = (float(v) for v in sys.argv[2:6])
zoom = float(sys.argv[6]) if len(sys.argv) > 6 else 6.0
step = float(sys.argv[7]) if len(sys.argv) > 7 else 0.5

doc = fitz.open(PDF)
page = doc[0]
x0, y0, x1, y1 = mx0 * PT_PER_M, my0 * PT_PER_M, mx1 * PT_PER_M, my1 * PT_PER_M
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(x0, y0, x1, y1))
img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()

def to_px(gx, gy):
    return (int(round((gx * PT_PER_M - x0) * zoom)), int(round((gy * PT_PER_M - y0) * zoom)))

step = step
gx = np.floor(mx0 / step) * step
while gx <= mx1 + 1e-9:
    p = to_px(gx, 0)[0]
    major = abs(gx / 1.0 - round(gx / 1.0)) < 1e-6
    col = (0, 0, 255) if major else (180, 180, 255)
    cv2.line(img, (p, 0), (p, img.shape[0]), col, 2 if major else 1, cv2.LINE_AA)
    cv2.putText(img, f"{gx:.1f}", (p + 3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 255), 1, cv2.LINE_AA)
    gx += step
gy = np.floor(my0 / step) * step
while gy <= my1 + 1e-9:
    p = to_px(0, gy)[1]
    major = abs(gy / 1.0 - round(gy / 1.0)) < 1e-6
    col = (0, 0, 255) if major else (180, 180, 255)
    cv2.line(img, (0, p), (img.shape[1], p), col, 2 if major else 1, cv2.LINE_AA)
    cv2.putText(img, f"{gy:.1f}", (4, p - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 255), 1, cv2.LINE_AA)
    gy += step

out = os.path.join(DATA, f"grid_{name}.png")
cv2.imwrite(out, img)
print("SAVED", out, img.shape)
