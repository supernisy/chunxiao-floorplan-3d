"""把当前 room-graph / walls_poly 反投影叠加到 CAD 图纸上，人眼核对分割正确性。

m -> pt: pt = PT_PER_M * m   (PT_PER_M = 45.36, 原点即 PDF 原点)

用法: python pipeline/overlay_pdf.py [x0 y0 x1 y1 zoom]
默认裁 公摊以外的整幅。
"""
import os, sys, json
import numpy as np
import cv2
import pymupdf as fitz

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M = 45.36

x0, y0, x1, y1 = (float(v) for v in sys.argv[1:5]) if len(sys.argv) > 4 else (120.0, 60.0, 820.0, 790.0)
zoom = float(sys.argv[5]) if len(sys.argv) > 5 else 2.6

doc = fitz.open(PDF)
page = doc[0]
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(x0, y0, x1, y1))
img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()

def to_px(m):
    return (int(round((m[0] * PT_PER_M - x0) * zoom)), int(round((m[1] * PT_PER_M - y0) * zoom)))

g = json.load(open(os.path.join(DATA, "..", "app", "src", "data", "room-graph.json"), encoding="utf-8"))
for i, r in enumerate(g["rooms"]):
    poly = np.array([to_px(p) for p in r["polygon_m"]], np.int32)
    cv2.polylines(img, [poly], True, (0, 0, 255), 1, cv2.LINE_AA)
    c = r.get("cent_m") or [np.mean([p[0] for p in r["polygon_m"]]),
                            np.mean([p[1] for p in r["polygon_m"]])]
    p = to_px(c)
    cv2.putText(img, r["id"], (p[0] - 8, p[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 200), 1, cv2.LINE_AA)

# 墙带（绿）
wp = os.path.join(ROOT, "app", "src", "data", "walls_poly.json")
if os.path.exists(wp):
    for b in json.load(open(wp, encoding="utf-8")):
        for ring in [b["shell"]] + b.get("holes", []):
            cv2.polylines(img, [np.array([to_px(p) for p in ring], np.int32)], True, (0, 170, 0), 1, cv2.LINE_AA)

# 门（蓝线 + 编号）
for d in g["doors"]:
    a, b = d["opening_m"]
    cv2.line(img, to_px(a), to_px(b), (255, 0, 0), 2, cv2.LINE_AA)
    p = to_px([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
    cv2.putText(img, d["id"] + ":" + d["type"], (p[0] + 4, p[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 0, 0), 1, cv2.LINE_AA)

out = os.path.join(DATA, "overlay_pdf.png")
cv2.imwrite(out, img)
print("SAVED", out, img.shape)
