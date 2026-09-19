"""
doors_v3.py — 门符号结构化解析（最终）。
事实：P-DOOR 中门扇=橙色 poly 长边；门弧=短碎线（灰或橙）拼成。
算法：簇内所有像素点到门扇线的最大距离 > 0.6m => 有门弧 => 平开门(swing)，否则垭口(opening)。
门洞：铰链 H = 门扇端（离弧远者）；另一端 O = H ± R90(F-H)，取更靠近墙 mask 的方向。
输出 data/door_symbols.json + data/doors_check.png
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

wall_img = cv2.imread(os.path.join(DATA, "mask_wall.png"), 0)
wall_dist_px = cv2.distanceTransform(255 - wall_img, cv2.DIST_L2, 3)


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


def wall_dist_m(p):
    px, py = to_px(p)
    if not (0 <= px < W and 0 <= py < H):
        return 99.0
    return float(wall_dist_px[py, px]) / ZOOM / PT_PER_M


items = layers["P-DOOR"]
img = np.zeros((H, W), np.uint8)
prims = []
for d in items:
    k = d["kind"]
    pts = [tuple(p) for p in d["pts"]]
    segs = []
    if k == "line":
        cv2.line(img, to_px(pts[0]), to_px(pts[-1]), 255, 2)
        segs = [(pts[0], pts[-1])]
    elif k == "curve":
        arr = np.array([to_px(p) for p in pts], np.int32)
        cv2.polylines(img, [arr], False, 255, 2)
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    elif k == "poly":
        arr = np.array([to_px(p) for p in pts], np.int32)
        cv2.polylines(img, [arr], True, 255, 2)
        segs = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    if segs:
        prims.append({"pts": pts, "segs": segs, "orange": d["color"] == "#FF7F00"})


def seglen(s):
    return math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1])


dil = cv2.dilate(img, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
n, lab, stats, cent = cv2.connectedComponentsWithStats(dil, connectivity=8)

res = []
for i in range(1, n):
    x, y, w, h, area = stats[i]
    if area < 200:
        continue
    mask = (lab == i)
    o_segs = []
    for pr in prims:
        if sum(1 for p in pr["pts"] if mask[min(H - 1, max(0, to_px(p)[1])), min(W - 1, max(0, to_px(p)[0]))]) / len(pr["pts"]) < 0.5:
            continue
        if pr["orange"]:
            o_segs.extend(pr["segs"])
    if not o_segs:
        continue
    leaf = max(o_segs, key=seglen)
    leaf_m = seglen(leaf) / PT_PER_M
    p0, p1 = leaf
    a, b = np.array(p0), np.array(p1)
    dd = b - a
    nrm = np.hypot(*dd) or 1e-9

    def dist_line(p):
        return abs(dd[0] * (p[1] - a[1]) - dd[1] * (p[0] - a[0])) / nrm

    # 簇内所有像素点（原始线）
    ys, xs = np.where((img > 0) & mask)
    pix = [(float(px) / ZOOM, float(py) / ZOOM) for px, py in zip(xs, ys)]
    maxd_m = max(dist_line(p) for p in pix) / PT_PER_M if pix else 0.0
    has_arc = maxd_m > 0.55

    if has_arc:
        arcp = [p for p in pix if dist_line(p) > 0.25 * PT_PER_M]
        d0 = min(math.hypot(p[0] - p0[0], p[1] - p0[1]) for p in arcp)
        d1 = min(math.hypot(p[0] - p1[0], p[1] - p1[1]) for p in arcp)
        hinge, free = (p0, p1) if d0 > d1 else (p1, p0)
        # 门洞另一端：垂直门扇方向的候选里，更贴墙者
        v = (free[0] - hinge[0], free[1] - hinge[1])
        nv = (-v[1], v[0])
        c1 = (hinge[0] + nv[0], hinge[1] + nv[1])
        c2 = (hinge[0] - nv[0], hinge[1] - nv[1])
        if arcp:
            dc1 = min(math.hypot(p[0] - c1[0], p[1] - c1[1]) for p in arcp)
            dc2 = min(math.hypot(p[0] - c2[0], p[1] - c2[1]) for p in arcp)
            other = c1 if dc1 <= dc2 else c2
        else:
            other = c1 if wall_dist_m(c1) < wall_dist_m(c2) else c2
        dtype = "swing"
    else:
        hinge, free, other = p0, p1, p1
        dtype = "opening"

    ow = math.hypot(other[0] - hinge[0], other[1] - hinge[1]) / PT_PER_M
    res.append({
        "cluster": i,
        "centroid_pt": [round(float(cent[i][0]) / ZOOM, 1), round(float(cent[i][1]) / ZOOM, 1)],
        "leaf_m": round(leaf_m, 3),
        "max_arc_dist_m": round(maxd_m, 3),
        "type": dtype,
        "opening_m": round(ow, 3),
        "hinge_pt": [round(v, 1) for v in hinge],
        "free_pt": [round(v, 1) for v in free],
        "opening_pt": [[round(v, 1) for v in hinge], [round(v, 1) for v in other]],
        "hinge_wall_dist_m": round(wall_dist_m(hinge), 3),
        "other_wall_dist_m": round(wall_dist_m(other), 3),
        "confidence": "high" if abs(ow - leaf_m) / max(leaf_m, 1e-6) < 0.35 else "low",
    })

res.sort(key=lambda r: (r["centroid_pt"][1], r["centroid_pt"][0]))
json.dump(res, open(os.path.join(DATA, "door_symbols.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"doors: {len(res)}\n")
print(f"{'#':>3} {'center_pt':>16} {'leaf_m':>7} {'open_m':>7} {'type':>8} {'arcMax':>7} {'wallH':>6} {'wallO':>6}")
for k, d in enumerate(res):
    print(f"{k:>3} {str(tuple(d['centroid_pt'])):>16} {d['leaf_m']:>7} {d['opening_m']:>7} "
          f"{d['type']:>8} {d['max_arc_dist_m']:>7} {d['hinge_wall_dist_m']:>6} {d['other_wall_dist_m']:>6}")

vis = np.zeros((H, W, 3), np.uint8)
vis[img > 0] = (130, 130, 130)
for d in res:
    h = [int(v * ZOOM) for v in d["opening_pt"][0]]
    o = [int(v * ZOOM) for v in d["opening_pt"][1]]
    cv2.circle(vis, tuple(h), 7, (0, 0, 255), -1)
    cv2.line(vis, tuple(h), tuple(o), (0, 255, 255), 4)
cv2.imwrite(os.path.join(DATA, "doors_check.png"), vis)
print("\nWROTE door_symbols.json + doors_check.png")
