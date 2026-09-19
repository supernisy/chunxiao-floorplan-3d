"""
rooms_v4.py — 最终房间多边形提取。
1) barrier = close(wall∪glass,61) ∪ door_sym(dilate15) ∪ 门洞线(延长)∪门扇线   [sym+leaf]
2) 连通域 -> 房间
3) watershed 把「门符号区域」按最近邻归还给各房间 -> 修复门弧造成的凹角
4) findContours + approxPolyDP -> 多边形(px -> pt -> m)
输出 data/rooms_final.json + data/rooms_final.png
"""
import json, os, math
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
meta = json.load(open(os.path.join(DATA, "masks_meta.json"), encoding="utf-8"))
scale = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
ZOOM = meta["zoom_px_per_pt"]
PT_PER_M = scale["points_per_meter"]
M_PER_PT = 1.0 / PT_PER_M
PX_PER_M = PT_PER_M * ZOOM

wall = cv2.imread(os.path.join(DATA, "mask_wall.png"), 0)
glass = cv2.imread(os.path.join(DATA, "mask_glass.png"), 0)
door_img = cv2.imread(os.path.join(DATA, "mask_door.png"), 0)
doors = json.load(open(os.path.join(DATA, "door_symbols.json"), encoding="utf-8"))
H, W = wall.shape


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


def ell(k):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


# ---- 双线墙 -> 实心墙 ----
def solid_wall(mask):
    """把「双线墙」变成真实厚度的实心墙。

    做法：找出被墙线**闭合围住**、且**短边 <= 0.3m**（即墙厚量级）的背景腔体，填实。

    ⚠️ 为什么不用 morphologyEx(CLOSE, 大核)：闭运算 = 膨胀+腐蚀，本质是**凸性填充**，
    在两条靠近但不平行的墙线之间会填出**楔形尖刺**。这些尖刺在 3D 拉伸时三角化
    （earcut）会崩成跨越整个房间的退化三角形 —— 俯视图里的大片灰色尖刺即由此而来。
    本方法逐腔体按「短边」判据填实，既不会膨胀墙的外轮廓，也不会产生楔形。
    """
    inv = cv2.bitwise_not(mask)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    out = mask.copy()
    filled = 0
    for i in range(1, n):
        x, y, w, h = [int(v) for v in stats[i, :4]]
        if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
            continue                        # 接触图像边界 = 外部大空间
        m = (lab == i).astype(np.uint8)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) <= 0.30 * PX_PER_M:   # 短边≈墙厚 -> 是墙的内腔
            out[m > 0] = 255
            filled += 1

    # ⚠️ 只填腔，**不做任何形态学后处理**。
    # 实测：ell(5~7) 的 opening、以及"删除远离腔体的孤立线"，都会破坏墙的连续性，
    # 房间数从 16 崩到 1~3。残留的斜楔（源于 P-WALL 里混的门洞示意线/斜线）
    # 改由 triangulate_walls.py 在**三角形层面**按"细长程度"剔除，几何无损。
    print(f"    solid_wall: filled {filled} inner cavities")
    return out


wall_solid = solid_wall(wall)
glass_solid = solid_wall(glass)

# ---- barrier ----
b = cv2.bitwise_or(wall_solid, glass_solid)
door_solid = cv2.dilate(door_img, ell(15))
b = cv2.bitwise_or(b, door_solid)
for d in doors:
    h = np.array(to_px(d["opening_pt"][0]), float)
    o = np.array(to_px(d["opening_pt"][1]), float)
    f = np.array(to_px(d["free_pt"]), float)
    v = o - h
    L = float(np.hypot(*v))
    if L < 1:
        continue
    u = v / L
    cv2.line(b, tuple(np.round(h - u * 0.45 * PX_PER_M).astype(int)),
             tuple(np.round(o + u * 0.45 * PX_PER_M).astype(int)), 255, 23)
    if d["type"] == "swing" and float(np.hypot(*(f - h))) > 1:
        cv2.line(b, tuple(np.round(h).astype(int)), tuple(np.round(f).astype(int)), 255, 23)

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
                  "cent_px": [float(cent[i][0]), float(cent[i][1])]})
rooms.sort(key=lambda r: -r["area_m2"])
print(f"segmented rooms: {len(rooms)}")

# ---- watershed 修复：门符号区域归还最近房间 ----
markers = np.zeros((H, W), np.int32)
for k, r in enumerate(rooms):
    markers[lab == r["cid"]] = k + 1
img3 = cv2.cvtColor(b, cv2.COLOR_GRAY2BGR)
ws = cv2.watershed(img3, markers.copy())
dr = door_solid > 0

vis = np.full((H, W, 3), 255, np.uint8)
vis[b > 0] = (80, 80, 80)
PALETTE = [(255, 190, 190), (190, 230, 190), (190, 210, 255), (255, 235, 170),
           (225, 200, 245), (185, 235, 235), (255, 215, 175), (215, 235, 175),
           (245, 195, 205), (195, 230, 245), (210, 210, 250), (240, 220, 190),
           (200, 245, 220), (250, 205, 225), (215, 245, 190), (235, 225, 205),
           (205, 215, 235), (230, 240, 215), (245, 220, 235), (215, 230, 240)]

out = []
final_lab = np.zeros((H, W), np.int32)
for k, r in enumerate(rooms):
    m = (lab == r["cid"]) | ((ws == k + 1) & dr)
    final_lab[m] = k + 1
    m = m.astype(np.uint8) * 255
    vis[m > 0] = PALETTE[k % len(PALETTE)]
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        continue
    c = max(cnts, key=cv2.contourArea)
    eps = max(1.5, 0.006 * cv2.arcLength(c, True))
    ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    poly_px = [[float(p[0]), float(p[1])] for p in ap]
    poly_m = [[round(p[0] / ZOOM * M_PER_PT, 4), round(p[1] / ZOOM * M_PER_PT, 4)] for p in ap]
    area_m2 = abs(cv2.contourArea(ap.astype(np.float32))) / PX_PER_M ** 2
    out.append({"idx": k, "cid": r["cid"],
                "cent_px": [round(r["cent_px"][0], 1), round(r["cent_px"][1], 1)],
                "cent_pt": [round(r["cent_px"][0] / ZOOM, 1), round(r["cent_px"][1] / ZOOM, 1)],
                "cent_m": [round(r["cent_px"][0] / ZOOM * M_PER_PT, 3), round(r["cent_px"][1] / ZOOM * M_PER_PT, 3)],
                "area_m2": round(area_m2, 2),
                "n_vertices": len(poly_px),
                "poly_m": poly_m})
    cx, cy = r["cent_px"]
    cv2.putText(vis, f"R{k}", (int(cx) - 26, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 200), 2)
    cv2.putText(vis, f"{area_m2:.1f}", (int(cx) - 34, int(cy) + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 120), 2)

final_lab_raw = np.zeros((H, W), np.int32)
for k, r in enumerate(rooms):
    final_lab_raw[lab == r["cid"]] = k + 1

json.dump({"zoom": ZOOM, "px_per_m": PX_PER_M, "pt_per_m": PT_PER_M,
           "rooms": out}, open(os.path.join(DATA, "rooms_final.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
np.save(os.path.join(DATA, "rooms_label.npy"), final_lab)
np.save(os.path.join(DATA, "rooms_label_raw.npy"), final_lab_raw)
# 墙带轮廓（壳 + 洞）供 3D 拉伸 —— 直接用实心墙，不用闭运算（避免楔形尖刺）
wall_band = wall_solid
cnts, hier = cv2.findContours(wall_band, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
hier = hier[0] if hier is not None else []


def _simplify(c):
    ap = cv2.approxPolyDP(c, max(1.2, 0.004 * cv2.arcLength(c, True)), True).reshape(-1, 2)
    return [[round(p[0] / ZOOM * M_PER_PT, 4), round(p[1] / ZOOM * M_PER_PT, 4)] for p in ap]


MIN_AREA_PX = (0.12 * PX_PER_M) ** 2
wpoly = []
for i, c in enumerate(cnts):
    if hier[i][3] != -1:
        continue  # 只取最外层轮廓
    if cv2.contourArea(c) < MIN_AREA_PX:
        continue
    shell = _simplify(c)
    holes = []
    ch = hier[i][2]
    while ch != -1:
        if cv2.contourArea(cnts[ch]) > MIN_AREA_PX:
            holes.append(_simplify(cnts[ch]))
        ch = hier[ch][0]
    wpoly.append({"shell": shell, "holes": holes})
print(f"wall bands: {len(wpoly)} (with holes: {sum(1 for w in wpoly if w['holes'])})")
json.dump(wpoly, open(os.path.join(DATA, "walls_poly.json"), "w", encoding="utf-8"), ensure_ascii=False)
cv2.imwrite(os.path.join(DATA, "rooms_final.png"), vis)
print(f"final rooms: {len(out)}")
for r in out:
    print(f"  R{r['idx']:<2} {r['area_m2']:>7}m2  cent_pt={r['cent_pt']}  verts={r['n_vertices']}")
print("WROTE rooms_final.json + rooms_final.png")
