"""
segment_v2.py — 在「墙∪门∪玻璃」mask 上做形态学闭合以填平门洞，取连通域得到房间。
输出各参数组合的房间统计 + 彩色调试图，用于挑选最佳参数。
"""
import json, os
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
meta = json.load(open(os.path.join(DATA, "masks_meta.json"), encoding="utf-8"))
scale = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
ZOOM = meta["zoom_px_per_pt"]
PT_PER_M = scale["points_per_meter"]
PX_PER_M = PT_PER_M * ZOOM
print(f"ZOOM={ZOOM}  PX_PER_M={PX_PER_M:.2f}  (1m = {PX_PER_M:.0f}px)")

combined = cv2.imread(os.path.join(DATA, "mask_closed.png"), 0)
H, W = combined.shape

PALETTE = [(255, 99, 71), (60, 179, 113), (65, 105, 225), (255, 215, 0),
           (186, 85, 211), (0, 206, 209), (255, 140, 0), (154, 205, 50),
           (220, 20, 60), (72, 209, 204), (123, 104, 238), (210, 105, 30),
           (0, 191, 255), (255, 20, 147), (50, 205, 50), (255, 165, 0)]


def segment(close_k, dil_k, min_area_m2=1.5):
    b = combined.copy()
    if close_k > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, k)
    if dil_k > 0:
        k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil_k, dil_k))
        b = cv2.dilate(b, k2)
    free = cv2.bitwise_not(b)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(free, connectivity=4)
    min_px = min_area_m2 * PX_PER_M ** 2
    rooms = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        x, y, w, h = int(stats[i, 0]), int(stats[i, 1]), int(stats[i, 2]), int(stats[i, 3])
        touches = (x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1)
        if area < min_px:
            continue
        if touches:
            continue
        rooms.append({"cid": i, "area_px": area, "area_m2": round(area / PX_PER_M ** 2, 2),
                      "bbox_px": [x, y, w, h],
                      "centroid_px": [round(float(cent[i][0]), 1), round(float(cent[i][1]), 1)]})
    rooms.sort(key=lambda r: -r["area_m2"])
    return lab, rooms, b


# 调试图用：把 rooms 上色
def make_debug(lab, rooms, tag):
    vis = cv2.cvtColor(combined, cv2.COLOR_GRAY2BGR)
    vis[combined > 0] = (200, 200, 200)
    for idx, r in enumerate(rooms):
        col = PALETTE[idx % len(PALETTE)]
        m = (lab == r["cid"])
        vis[m] = col
        cx, cy = int(r["centroid_px"][0]), int(r["centroid_px"][1])
        cv2.putText(vis, str(idx), (cx - 10, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 3)
        cv2.putText(vis, str(idx), (cx - 10, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 1)
    cv2.imwrite(os.path.join(DATA, f"seg_{tag}.png"), vis)


report = []
for (ck, dk) in [(15, 7), (25, 13), (35, 19), (45, 25), (61, 31)]:
    lab, rooms, b = segment(ck, dk)
    tag = f"c{ck}_d{dk}"
    make_debug(lab, rooms, tag)
    line = f"close={ck} dilate={dk} -> {len(rooms)} rooms: " + ", ".join(
        f"{r['area_m2']}m2@({r['centroid_px'][0]:.0f},{r['centroid_px'][1]:.0f})" for r in rooms)
    print(line)
    report.append(line)

open(os.path.join(DATA, "seg_report.txt"), "w", encoding="utf-8").write("\n".join(report))
print("DONE")
