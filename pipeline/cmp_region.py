"""cmp_region.py — 把同一米制矩形区域的「PDF 原图 / 墙掩膜 / 房间分割」并排输出，用于人眼比对。

用法: python pipeline/cmp_region.py out.png mx0 my0 mx1 my1 [zoom]
"""
import os, sys, json
import numpy as np, cv2, fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M = 45.36
PP = 200.0

out = sys.argv[1]
mx0, my0, mx1, my1 = (float(v) for v in sys.argv[2:6])
zoom = float(sys.argv[6]) if len(sys.argv) > 6 else 4.0
VER = sys.argv[7] if len(sys.argv) > 7 else "v6"


def crop(img, sx, sy, w, h, scale):
    """img: 已按 PP px/m 栅格化；返回 (sx,sy) 米为左上、宽 w 高 h 米的放大裁剪。"""
    x0, y0 = int(sx * PP), int(sy * PP)
    x1, y1 = int((sx + w) * PP), int((sy + h) * PP)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.shape[1], x1), min(img.shape[0], y1)
    c = img[y0:y1, x0:x1]
    return cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


w, h = mx1 - mx0, my1 - my0
sc = zoom / PP * PP / PP  # 相对 PP 的放大倍数
scale = zoom * PP / PP

# 1) PDF 原图：按 PP px/m 渲染
doc = fitz.open(PDF)
pg = doc[0]
m = PP / PT_PER_M                  # pt -> px，与 geom_v5.to_px 完全一致
pix = pg.get_pixmap(matrix=fitz.Matrix(m, m), colorspace=fitz.csRGB, alpha=False)
arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
pdf_img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
print("PDF raster", pdf_img.shape, "期望H,W =", int(842 / PT_PER_M * PP) + 2, int(1191 / PT_PER_M * PP) + 2)

# 2) 墙掩膜
wall = cv2.imread(os.path.join(DATA, VER, "wall.png"), 0)
wallc = cv2.cvtColor(wall, cv2.COLOR_GRAY2BGR)
# 3) 房间
vis = cv2.imread(os.path.join(DATA, VER, "rooms_vis.png"))
# 4) 门/玻璃符号
door = cv2.imread(os.path.join(DATA, VER, "seal_inst.png"), 0)
doorc = cv2.cvtColor(door, cv2.COLOR_GRAY2BGR)

parts = []
for im, tag in [(pdf_img, "PDF"), (wallc, "WALL"), (vis, "ROOMS"), (doorc, "DOOR")]:
    c = crop(im, mx0, my0, w, h, scale)
    c = cv2.copyMakeBorder(c, 26, 4, 4, 4, cv2.BORDER_CONSTANT, value=(40, 40, 40))
    cv2.putText(c, tag, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    parts.append(c)
NCOL = 2
while len(parts) % NCOL:
    parts.append(np.zeros_like(parts[0]))
rows = [np.hstack(parts[i:i + NCOL]) for i in range(0, len(parts), NCOL)]
canvas = np.vstack(rows)
cv2.imwrite(out, canvas)
print("写", out, canvas.shape)
