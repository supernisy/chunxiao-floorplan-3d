"""diag_2d.py — 纯诊断：把 rooms_final.json 的房间 + walls_poly.json 的墙带
并排画成 2D PNG，用于肉眼比对房间形状与平面图是否一致、墙带是否成条带。

用法：python pipeline/diag_2d.py [walls_json] [out_png]
默认 walls_json=data/walls_poly.json，out=data/diag_2d.png
"""
import json, os, sys
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")

walls_json = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "walls_poly.json")
out_png = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DATA, "diag_2d.png")
rooms_json = sys.argv[3] if len(sys.argv) > 3 else os.path.join(DATA, "rooms_final.json")

rooms = json.load(open(rooms_json, encoding="utf-8"))
walls = json.load(open(walls_json, encoding="utf-8"))

# rooms 可能是 rooms_final（poly_m + idx）或 room-graph（polygon_m + id/name）
def room_poly(r):
    return r.get("poly_m") or r.get("polygon_m")

def room_label(r, i):
    if "name" in r:
        return r.get("id", f"R{i}")
    return f"R{r.get('idx', i)}"

# 收集所有点求 bbox
allp = []
for r in rooms["rooms"]:
    allp += [list(p) for p in room_poly(r)]
for w in walls:
    allp += [list(p) for p in w["shell"]]
for w in walls:
    for h in w.get("holes", []):
        allp += [list(p) for p in h]
allp = np.array(allp, float)
mn = allp.min(axis=0) - 0.6
mx = allp.max(axis=0) + 0.6
S = 55.0
H = int((mx[1] - mn[1]) * S)
W = int((mx[0] - mn[0]) * S)

def px(p):
    return (int((p[0] - mn[0]) * S), int((p[1] - mn[1]) * S))

PALETTE = [(230,217,198),(198,224,230),(214,230,198),(230,198,214),(238,224,190),
           (205,205,235),(220,230,205),(240,205,205),(210,225,235),(235,220,240),
           (225,235,210),(200,215,205),(245,225,205),(215,210,230),(230,235,235),
           (235,215,225)]

# --- 图A：房间 ---
imgA = np.full((H, W, 3), 255, np.uint8)
for i, r in enumerate(rooms["rooms"]):
    poly = np.array([px(p) for p in room_poly(r)], np.int32)
    cv2.fillPoly(imgA, [poly], PALETTE[i % len(PALETTE)])
    cv2.polylines(imgA, [poly], True, (60, 60, 60), 1)
    pm = room_poly(r)
    c = r.get("cent_m") or [np.mean([p[0] for p in pm]), np.mean([p[1] for p in pm])]
    cv2.putText(imgA, room_label(r, i), (px(c)[0] - 8, px(c)[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, (20, 20, 20), 1, cv2.LINE_AA)
cv2.imwrite(out_png.replace(".png", "_rooms.png"), imgA)

# --- 图B：墙带（填充） ---
imgB = np.full((H, W, 3), 255, np.uint8)
for w in walls:
    sh = np.array([px(p) for p in w["shell"]], np.int32)
    cv2.fillPoly(imgB, [sh], (120, 120, 120))
    for h in w.get("holes", []):
        hh = np.array([px(p) for p in h], np.int32)
        cv2.fillPoly(imgB, [hh], (255, 255, 255))
    cv2.polylines(imgB, [sh], True, (40, 40, 40), 1)
cv2.imwrite(out_png.replace(".png", "_walls.png"), imgB)

# --- 图C：叠加（房间轮廓 + 墙带） ---
imgC = np.full((H, W, 3), 255, np.uint8)
for i, r in enumerate(rooms["rooms"]):
    poly = np.array([px(p) for p in room_poly(r)], np.int32)
    cv2.polylines(imgC, [poly], True, (200, 200, 200), 1)
for w in walls:
    sh = np.array([px(p) for p in w["shell"]], np.int32)
    cv2.fillPoly(imgC, [sh], (90, 90, 90))
    for h in w.get("holes", []):
        hh = np.array([px(p) for p in h], np.int32)
        cv2.fillPoly(imgC, [hh], (255, 255, 255))
cv2.imwrite(out_png, imgC)

print(f"rooms={len(rooms['rooms'])} walls={len(walls)}  -> {out_png}(_rooms/_walls)")
print("img size", imgC.shape)
