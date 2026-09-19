"""
analyze_doors2.py — 从 P-DOOR 的橙色门符号图元（#FF7F00）聚类出独立门符号，
每簇输出 bbox / 最长线段（=门扇）/ 是否有弧 / 门宽（米）。
"""
import json, os, math
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
layers = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))
S = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
PT_PER_M = S["points_per_meter"]
ZOOM = 3.0
W_PT, H_PT = 1016.0, 841.0
W, H = int(W_PT * ZOOM), int(H_PT * ZOOM)


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


items = [d for d in layers["P-DOOR"] if d["color"] == "#FF7F00"]
print("orange door items:", len(items))

img = np.zeros((H, W), np.uint8)
segs = []  # (L_pt, p0, p1, kind)
for d in items:
    if d["kind"] == "line":
        p0, p1 = d["pts"][0], d["pts"][1]
        cv2.line(img, to_px(p0), to_px(p1), 255, 2)
        segs.append((math.hypot(p1[0] - p0[0], p1[1] - p0[1]), p0, p1, "line"))
    elif d["kind"] in ("curve", "poly"):
        pts = d["pts"]
        arr = np.array([to_px(p) for p in pts], np.int32)
        cv2.polylines(img, [arr], d["kind"] == "poly", 255, 2)
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            segs.append((math.hypot(p1[0] - p0[0], p1[1] - p0[1]), p0, p1, "arc"))

cv2.imwrite(os.path.join(DATA, "door_symbols.png"), img)

dil = cv2.dilate(img, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (23, 23)))
n, lab, stats, cent = cv2.connectedComponentsWithStats(dil, connectivity=8)
print("clusters:", n - 1)

results = []
for i in range(1, n):
    x, y, w, h, area = stats[i]
    if area < 200:
        continue
    mask = (lab == i)
    # 落在该簇内的线段（用中点判断）
    in_segs = []
    for (L, p0, p1, kind) in segs:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        px, py = int(mx * ZOOM), int(my * ZOOM)
        if 0 <= py < H and 0 <= px < W and mask[py, px]:
            in_segs.append((L, p0, p1, kind))
    if not in_segs:
        continue
    longest = max(in_segs, key=lambda t: t[0])
    has_arc = any(s[3] == "arc" for s in in_segs)
    # 该簇的世界范围（pt）
    ys, xs = np.where(mask)
    results.append({
        "cluster": i,
        "bbox_pt": [round(x / ZOOM, 1), round(y / ZOOM, 1), round((x + w) / ZOOM, 1), round((y + h) / ZOOM, 1)],
        "centroid_pt": [round(cent[i][0] / ZOOM, 1), round(cent[i][1] / ZOOM, 1)],
        "leaf_len_m": round(longest[0] / PT_PER_M, 3),
        "leaf_p0": [round(v, 1) for v in longest[1]],
        "leaf_p1": [round(v, 1) for v in longest[2]],
        "has_arc": has_arc,
        "n_segs": len(in_segs),
    })

results.sort(key=lambda r: (r["centroid_pt"][1], r["centroid_pt"][0]))
print(f"\n{'#':>3} {'center_pt':>18} {'leaf_m':>7} {'arc':>4}  leaf endpoints")
for k, r in enumerate(results):
    print(f"{k:>3} {str(tuple(r['centroid_pt'])):>18} {r['leaf_len_m']:>7} {str(r['has_arc']):>5}  {r['leaf_p0']} -> {r['leaf_p1']}")
json.dump(results, open(os.path.join(DATA, "door_symbols.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\nWROTE door_symbols.json", len(results))
