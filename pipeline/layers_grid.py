"""
layers_grid.py — 把 GROUP_WALL 候选图层逐个单独渲染，拼成对照图，
用于定位「哪一层藏了厨房橱柜/台面轮廓」这类污染源。

输出：data/layers_grid.png
"""
import json, os
import cv2
import numpy as np

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
layers = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

ZOOM = 3.0
W, H = 3048, 2523


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


def draw(img, items, th=2):
    for it in items:
        k, pts = it["kind"], it["pts"]
        if not pts:
            continue
        try:
            if k == "line" and len(pts) >= 2:
                cv2.line(img, to_px(pts[0]), to_px(pts[1]), 255, th)
            elif k == "rect" and len(pts) >= 2:
                cv2.rectangle(img, to_px(pts[0]), to_px(pts[1]), 255, th)
            else:
                arr = np.array([to_px(p) for p in pts], np.int32)
                cv2.polylines(img, [arr], k in ("poly", "quad"), 255, th)
        except Exception:
            pass


TARGETS = [
    ("P-WALL", "P-WALL"),
    ("A-通-墙...........COMM-WALL", "COMM-WALL"),
    ("S-柱墙-填充.......COLUWL-HATCH", "COLUWL-HATCH"),
    ("S-柱墙-模板线.....COLUWL-LINE1", "COLUWL-LINE1"),
    ("户型刷图层$0$A-WALL-FNSH", "A-WALL-FNSH"),
    ("P-WALL FIN", "P-WALL-FIN"),
]

tiles = []
for key, label in TARGETS:
    img = np.zeros((H, W), np.uint8)
    if key in layers:
        draw(img, layers[key])
        n = len(layers[key])
    else:
        n = -1
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    small = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    cv2.putText(small, f"{label} n={n}", (12, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    tiles.append(small)
    print(f"{label}: n={n}")

rows = [np.hstack(tiles[0:2]), np.hstack(tiles[2:4]), np.hstack(tiles[4:6])]
grid = np.vstack(rows)
cv2.imwrite(os.path.join(DATA, "layers_grid.png"), grid)
print("WROTE data/layers_grid.png", grid.shape)
