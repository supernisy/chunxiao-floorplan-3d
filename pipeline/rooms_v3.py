"""
rooms_v3.py — 房间分割：实心墙带(close 61) + 门洞封堵。
对比三种封堵策略，选房间数/面积最合理者。
A) 门符号 mask 膨胀作障碍   B) 门洞线段两端各延长 0.35m 作障碍   C) 两者叠加
"""
import json, os
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
meta = json.load(open(os.path.join(DATA, "masks_meta.json"), encoding="utf-8"))
scale = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
ZOOM = meta["zoom_px_per_pt"]
PX_PER_M = scale["points_per_meter"] * ZOOM

wall = cv2.imread(os.path.join(DATA, "mask_wall.png"), 0)
glass = cv2.imread(os.path.join(DATA, "mask_glass.png"), 0)
door_img = cv2.imread(os.path.join(DATA, "mask_door.png"), 0)
doors = json.load(open(os.path.join(DATA, "door_symbols.json"), encoding="utf-8"))
H, W = wall.shape


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


def ell(k):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def build(kind):
    b = cv2.bitwise_or(wall, glass)
    b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, ell(61))
    if "sym" in kind:
        b = cv2.bitwise_or(b, cv2.dilate(door_img, ell(15)))
    if "line" in kind:
        for d in doors:
            h = np.array(to_px(d["opening_pt"][0]), float)
            o = np.array(to_px(d["opening_pt"][1]), float)
            v = o - h
            L = float(np.hypot(*v))
            if L < 1:
                continue
            u = v / L
            h2 = h - u * 0.35 * PX_PER_M
            o2 = o + u * 0.35 * PX_PER_M
            cv2.line(b, tuple(np.round(h2).astype(int)), tuple(np.round(o2).astype(int)), 255, 15)
    if "leaf" in kind:
        # 门洞线(延长) + 门扇线：直线段封门洞，但不切掉房间面积
        for d in doors:
            h = np.array(to_px(d["opening_pt"][0]), float)
            o = np.array(to_px(d["opening_pt"][1]), float)
            f = np.array(to_px(d["free_pt"]), float)
            v = o - h
            L = float(np.hypot(*v))
            if L < 1:
                continue
            u = v / L
            h2 = h - u * 0.45 * PX_PER_M
            o2 = o + u * 0.45 * PX_PER_M
            cv2.line(b, tuple(np.round(h2).astype(int)), tuple(np.round(o2).astype(int)), 255, 23)
            if d["type"] == "swing" and float(np.hypot(*(f - h))) > 1:
                cv2.line(b, tuple(np.round(h).astype(int)), tuple(np.round(f).astype(int)), 255, 23)
    return b


PALETTE = [(255, 190, 190), (190, 230, 190), (190, 210, 255), (255, 235, 170),
           (225, 200, 245), (185, 235, 235), (255, 215, 175), (215, 235, 175),
           (245, 195, 205), (195, 230, 245), (210, 210, 250), (240, 220, 190),
           (200, 245, 220), (250, 205, 225), (215, 245, 190), (235, 225, 205),
           (205, 215, 235), (230, 240, 215), (245, 220, 235), (215, 230, 240)]

for kind in ["leaf", "sym+leaf"]:
    b = build(kind)
    free = cv2.bitwise_not(b)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(free, connectivity=4)
    rooms = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        x, y, w, h = [int(v) for v in stats[i, :4]]
        if area < 1.2 * PX_PER_M ** 2:
            continue
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
            continue
        rooms.append({"cid": i, "area_m2": round(area / PX_PER_M ** 2, 2),
                      "cent_px": [round(float(cent[i][0]), 1), round(float(cent[i][1]), 1)]})
    rooms.sort(key=lambda r: -r["area_m2"])
    print(f"[{kind}] {len(rooms)} rooms, total {sum(r['area_m2'] for r in rooms):.1f} m2")
    for k, r in enumerate(rooms):
        print(f"   R{k:<2} {r['area_m2']:>7}m2  pt=({r['cent_px'][0]/ZOOM:.0f},{r['cent_px'][1]/ZOOM:.0f})")
    print()

    vis = np.full((H, W, 3), 255, np.uint8)
    vis[b > 0] = (70, 70, 70)
    for k, r in enumerate(rooms):
        vis[lab == r["cid"]] = PALETTE[k % len(PALETTE)]
        cx, cy = r["cent_px"]
        cv2.putText(vis, f"R{k}", (int(cx) - 26, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 200), 2)
    tag = kind.replace("+", "_")
    cv2.imwrite(os.path.join(DATA, f"rooms_{tag}.png"), vis)

    if kind == "sym+line":
        json.dump({"kind": kind, "zoom": ZOOM, "px_per_m": PX_PER_M, "rooms": rooms},
                  open(os.path.join(DATA, "rooms.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
print("DONE")
