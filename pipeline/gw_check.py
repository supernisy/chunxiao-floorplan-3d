"""gw_check.py — 公卫(厨房旁)专项核对图。

叠加：PDF 原图(淡化) + 我的墙体掩膜(半透明红) + 我的房间多边形(绿) + 我的门窗(蓝/紫)
用法: python pipeline/gw_check.py <x0> <y0> <x1> <y1> <out.png> [ppm]
"""
import json, sys
import numpy as np, cv2, pymupdf

ROOT = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
PT_PER_M = 45.36
PP = 200.0                      # 掩膜分辨率 px/m（与管线一致）

a = sys.argv[1:]
x0, y0, x1, y1 = (float(v) for v in a[:4])
out = a[4]
ppm = float(a[5]) if len(a) > 5 else 300.0

doc = pymupdf.open(f"{ROOT}/assets/chunxiao.pdf")
pg = doc[0]
S = ppm / PT_PER_M
pix = pg.get_pixmap(matrix=pymupdf.Matrix(S, S), colorspace=pymupdf.csRGB, alpha=False)
base = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
base = cv2.cvtColor(base, cv2.COLOR_RGB2BGR)
base = cv2.addWeighted(base, 0.45, np.full_like(base, 255), 0.55, 0)
W, H = int((x1 - x0) * ppm) + 1, int((y1 - y0) * ppm) + 1
img = base[:H, :W].copy()


def P(x, y):
    return (int((x - x0) * ppm), int((y - y0) * ppm))


# --- 我的墙体掩膜 ---
try:
    wm = cv2.imread(f"{ROOT}/data/v6/wall.png", 0)
    sub = wm[int(y0 * PP):int(y1 * PP), int(x0 * PP):int(x1 * PP)]
    sub = cv2.resize(sub, (W, H), interpolation=cv2.INTER_NEAREST)
    img[sub > 0] = (img[sub > 0] * 0.35 + np.array([60, 60, 235]) * 0.65).astype(np.uint8)
except Exception as e:
    print("wall mask skip:", e)

# --- 我的房间多边形 / 门窗 ---
g = json.load(open(f"{ROOT}/app/src/data/room-graph.json", encoding="utf-8"))
for r in g["rooms"]:
    pts = np.array([P(*p) for p in r["polygon_m"]], np.int32)
    col = (0, 170, 0)
    if "公卫" in r["name"]:
        col = (0, 215, 0)
    cv2.polylines(img, [pts], True, col, 2)
    cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
    side = 0.34 * ppm
    lx = int(np.clip(cx + side, 5, W - 200))
    ly = int(np.clip(cy - side, 16, H - 6))
    cv2.putText(img, r["id"], (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 120, 0), 2)
for d in g["doors"]:
    o = d.get("opening_m")
    if not o:
        continue
    col = (200, 0, 200) if d["type"] == "swing" else (255, 130, 0)
    cv2.line(img, P(*o[0]), P(*o[1]), col, 4)
    mx = int(np.clip((o[0][0] + o[1][0]) / 2 * ppm - x0 * ppm, 5, W - 60),)
    my = int(np.clip((o[0][1] + o[1][1]) / 2 * ppm - y0 * ppm, 16, H - 6))
    cv2.putText(img, d["id"], (mx, my), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 0, 150), 1)
for w in g.get("windows", []):
    o = w["opening_m"]
    cv2.line(img, P(*o[0]), P(*o[1]), (170, 0, 170), 3)

# 网格
import math
step = 0.5
gx = math.ceil(x0 / step) * step
while gx < x1:
    px = int((gx - x0) * ppm)
    cv2.line(img, (px, 0), (px, H), (0, 0, 220), 1)
    cv2.putText(img, f"{gx:g}", (px + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 180), 1)
    gx += step
gy = math.ceil(y0 / step) * step
while gy < y1:
    py = int((gy - y0) * ppm)
    cv2.line(img, (0, py), (W, py), (0, 0, 220), 1)
    cv2.putText(img, f"{gy:g}", (2, py + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 180), 1)
    gy += step

cv2.imwrite(out, img)
print("SAVED", out, img.shape)
