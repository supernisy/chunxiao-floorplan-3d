"""
pwall_colors.py — 把 P-WALL 按颜色拆开渲染，判断哪种颜色是「真墙」、哪种是别的东西。
输出：data/pwall_colors.png
"""
import json, os
import cv2
import numpy as np

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
d = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

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
            else:
                arr = np.array([to_px(p) for p in pts], np.int32)
                cv2.polylines(img, [arr], k in ("poly", "quad"), 255, th)
        except Exception:
            pass


TARGETS = [
    ("P-WALL", "#0000FF", "P-WALL blue"),
    ("P-WALL", "#FF00FF", "P-WALL magenta"),
]

tiles = []
for layer, color, label in TARGETS:
    img = np.zeros((H, W), np.uint8)
    items = [it for it in d.get(layer, []) if it["color"] == color]
    draw(img, items)
    s = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    s = cv2.cvtColor(s, cv2.COLOR_GRAY2BGR)
    cv2.putText(s, f"{label} n={len(items)}", (12, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    tiles.append(s)
    print(f"{label}: n={len(items)}")

cv2.imwrite(os.path.join(DATA, "pwall_colors.png"), np.hstack(tiles))
print("WROTE data/pwall_colors.png")
