"""geom_v5.py — 从 CAD 矢量层重建**严格正交**的墙与房间几何。

核心实测结论（决定本脚本的取舍）：
  · 所有墙类图层（P-WALL / P-WALL FIN / COMM-WALL / COLUWL-LINE1 /
    P-DOOR / COMM-GLAZ-SECT）的长段都是**精确轴向（偏差 0.0°）**；
  · 唯一带斜线的是 `S-柱墙-填充 COLUWL-HATCH` 的**斜向填充线**（2.5°~8°）。
  旧管线把 COLUWL-HATCH 整层当墙 → 斜填充线进入掩膜 → 黑三角/斜墙/房间不规则。
  本脚本对墙层做**轴向过滤**（|偏差| > TOL 的段整段丢弃），从源头保证 0/90 度。

图层语义（图例判读依据）：
  P-WALL(#0000FF 蓝 / #FF00FF 品红)  墙体
  P-WALL FIN(#00FFFF 青)             墙面面层（含真墙线）
  A-通-墙 COMM-WALL(#FFFF00 黄)       通用墙
  S-柱墙-模板线 COLUWL-LINE1(#FF3F00) 混凝土墙模板线
  S-柱墙-填充 COLUWL-HATCH(#808080 灰) 混凝土填充（含斜向填充线，只取轴向段）
  P-DOOR(#808080 灰=门扇/框, #FF7F00 橙=开启弧)  门
  A-通-门窗剖线 COMM-GLAZ-SECT(#DDA56E 棕)      门窗玻璃剖线
  A-平-栏杆扶手 FLOR-RAIL(#5CB800 绿)           栏杆（飘窗/阳台）

输出（app/src/data/）：
  walls_poly.json   墙实体（直角多边形，shell+holes）
  room-graph.json   房间（直角多边形）+ 门
  roof_poly.json    外轮廓
另存中间调试图到 data/。
"""
import os, sys, json, math
import numpy as np
import cv2
from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
APPDATA = os.path.join(ROOT, "app", "src", "data")
PT_PER_M = 45.36
PP = 200.0                          # px per meter
PAGE_W_PT, PAGE_H_PT = 1191.0, 842.0
AXIS_TOL_DEG = 1.0                  # 墙段允许的最大轴向偏差
CLOSE_M = 0.26                      # 墙双线闭合成实体的核尺寸（m）

W, H = int(PAGE_W_PT / PT_PER_M * PP) + 2, int(PAGE_H_PT / PT_PER_M * PP) + 2

LAYERS = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

# (图层名, 是否做轴向过滤)
WALL_SPEC = [
    ("P-WALL", True),
    ("P-WALL FIN", True),
    ("A-通-墙...........COMM-WALL", True),
    ("S-柱墙-模板线.....COLUWL-LINE1", True),
    ("S-柱墙-填充.......COLUWL-HATCH", True),
]
SEAL_SPEC = [
    ("P-DOOR", True),
    ("A-通-门窗剖线.....COMM-GLAZ-SECT", True),
    # 栏杆扶手：阳台/飘窗的外沿。不封堵的话 flood fill 会从阳台漏到室内。
    ("A-平-栏杆扶手.....FLOR-RAIL", True),
]


def to_px(p):
    """矢量坐标单位是 PDF point；pt -> m -> px。"""
    return (int(round(p[0] / PT_PER_M * PP)), int(round(p[1] / PT_PER_M * PP)))


def _axis_ok(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return False
    ang = math.degrees(math.atan2(abs(dy), abs(dx)))
    return min(ang, 90 - ang) <= AXIS_TOL_DEG


def _draw(img, it, thickness):
    k, pts = it.get("kind"), it.get("pts") or []
    if len(pts) < 2:
        return
    if k == "poly":
        arr = np.array([to_px(p) for p in pts], np.int32)
        cv2.fillPoly(img, [arr], 255)
        return
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if not _axis_ok(a, b):
            continue                      # 斜段整段丢弃 —— 正交性的根本保证
        cv2.line(img, to_px(a), to_px(b), 255, thickness, cv2.LINE_8)


def raster(spec, thickness=None):
    img = np.zeros((H, W), np.uint8)
    drawn = {}
    for name, axis_only in spec:
        items = LAYERS.get(name)
        if items is None:
            print("  [warn] 图层不存在:", name)
            continue
        n = 0
        for it in items:
            wpt = it.get("width") or 0.72
            th = thickness if thickness is not None else max(2, min(6, int(round(wpt * PP / PT_PER_M)) + 2))
            _draw(img, it, th)
            n += 1
        drawn[name] = n
    return img, drawn


def drop_small(mask, min_area_m2):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = np.zeros_like(mask)
    lim = min_area_m2 * PP * PP
    kept = 0
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= lim:
            out[lab == i] = 255
            kept += 1
    return out, kept, n - 1


def stage_wall():
    raw, drawn = raster(WALL_SPEC)
    print("  栅格化图元:", drawn)
    k = int(round(CLOSE_M * PP)) | 1
    solid = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    solid, kept, tot = drop_small(solid, 0.04)
    print(f"  墙闭合 k={k}px({CLOSE_M}m)  连通域 {tot} -> 保留 {kept}")
    return raw, solid


def stage_seal():
    """门/玻璃符号掩膜：分割房间时用来堵洞口。"""
    raw, drawn = raster(SEAL_SPEC)
    k = int(round(0.12 * PP)) | 1
    s = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    d = int(round(0.05 * PP)) | 1
    s = cv2.dilate(s, np.ones((d, d), np.uint8))
    print("  门/玻璃封堵:", drawn, " 像素", int((raw > 0).sum()))
    return raw, s


EXCLUDE_NAMES = {"电梯厅", "楼梯间", "消防电梯", "普通电梯", "前室", "管井"}


def build_scope(PP):
    """用旧房间集（16 间，含公摊）的并集当"考察范围"。

    为什么不靠 flood fill 判外部：室外/阳台栏杆若有断口，flood 会漏进室内，
    整个 LDK 会被误判成"外部"。用旧房间集当 scope 从根上避开这个坑。
    """
    old = json.load(open(os.path.join(DATA, "room-graph.json"), encoding="utf-8"))
    scope = np.zeros((H, W), np.uint8)
    for r in old["rooms"]:
        pts = np.array([[int(round(p[0] * PP)), int(round(p[1] * PP))] for p in r["polygon_m"]], np.int32)
        cv2.fillPoly(scope, [pts], 255)
    k = int(round(0.35 * PP)) | 1
    return cv2.dilate(scope, np.ones((k, k), np.uint8)), old


def classify(op, door_raw, glass_raw, lab, room_of, probe=0.30):
    """按图例（PDF 图层含义）给洞口定类型：

      · 平开门 swing   —— 门扇 + 开启弧。特征：门像素在**垂直墙向**伸出 > 0.40m
                          （门扇画在开启位置，长度≈门宽）。对应 P-DOOR #808080/#FF7F00。
      · 推拉/移门 sliding —— 两扇门平行、错开叠放，**没有开启弧**。
                          特征：门像素只贴着墙走（垂直伸出 < 0.40m）。
      · 玻璃隔断 glass  —— 只有门窗剖线 COMM-GLAZ-SECT，无门扇。
      · 洞口 opening   —— 墙上只有空白，什么都没画。
      · 窗 window      —— 洞口一侧不是房间（位于外墙上）。
    """
    a, b = op["opening_m"]
    P = int(round(probe * PP))
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    lx = int(round(mid[0] * PP))
    ly = int(round(mid[1] * PP))
    if op["ori"] == "h":
        la = lab[max(0, ly - P), lx]
        lb = lab[min(H - 1, ly + P), lx]
    else:
        la = lab[ly, max(0, lx - P)]
        lb = lab[ly, min(W - 1, lx + P)]
    op["room_ids"] = [room_of.get(int(la)), room_of.get(int(lb))]
    both = op["room_ids"][0] and op["room_ids"][1] and op["room_ids"][0] != op["room_ids"][1]

    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    if op["ori"] == "h":
        x0 -= 0.05; x1 += 0.05; y0 -= 0.45; y1 += 0.45
    else:
        y0 -= 0.05; y1 += 0.05; x0 -= 0.45; x1 += 0.45
    px0, py0 = int(max(0, x0 * PP)), int(max(0, y0 * PP))
    px1, py1 = int(min(W, x1 * PP)), int(min(H, y1 * PP))
    sub_d = door_raw[py0:py1, px0:px1]
    sub_g = glass_raw[py0:py1, px0:px1]
    nd, ng = int((sub_d > 0).sum()), int((sub_g > 0).sum())
    perp = 0.0
    if nd > 0:
        ys, xs = np.nonzero(sub_d > 0)
        if op["ori"] == "h":
            perp = float(np.max(np.abs((ys + py0) / PP - b[1])))
        else:
            perp = float(np.max(np.abs((xs + px0) / PP - b[0])))
    if not both:
        t = "window"
    elif perp > 0.40:
        t = "swing"
    elif nd > 0:
        t = "sliding"
    elif ng > 0:
        t = "glass"
    else:
        t = "opening"
    op["type"] = t
    op["_perp"] = round(perp, 3)
    op["_door_px"] = nd
    op["_glass_px"] = ng
    return op


def stage_rooms(wall, seal, scope):
    barrier = cv2.bitwise_or(wall, seal)
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    interior = ((barrier == 0) & (scope > 0)).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(interior, 4)
    keep, drop = [], 0
    lim = 0.45 * PP * PP
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < lim:
            drop += 1
            continue
        keep.append(i)
    print(f"  连通域 {n-1} -> 保留 {len(keep)}（剔小 {drop}）")
    return lab, stats, cent, keep


def name_components(lab, keep, old):
    """按与旧房间的重叠面积继承名字。"""
    old_masks = []
    for r in old["rooms"]:
        m = np.zeros((H, W), np.uint8)
        pts = np.array([[int(round(p[0] * PP)), int(round(p[1] * PP))] for p in r["polygon_m"]], np.int32)
        cv2.fillPoly(m, [pts], 255)
        old_masks.append((r["name"], r["id"], m))
    out = {}
    for k in keep:
        comp = (lab == k)
        best, best_ov = None, 0
        for nm, rid, m in old_masks:
            ov = int(np.count_nonzero(comp & (m > 0)))
            if ov > best_ov:
                best_ov, best = ov, (nm, rid)
        area = int(np.count_nonzero(comp))
        out[k] = {"name": best[0] if best and best_ov > 0.25 * area else "未命名",
                  "old_id": best[1] if best else None,
                  "match": best_ov / max(area, 1)}
    return out


# ---------- 门窗：在墙上找洞口，再按图例分类 ----------

def _runs(line):
    segs, s = [], None
    for i, v in enumerate(line):
        if v and s is None:
            s = i
        elif not v and s is not None:
            segs.append((s, i))
            s = None
    if s is not None:
        segs.append((s, len(line)))
    return segs


def detect_gaps(wall, min_w=0.55, max_w=2.8, win=0.9, cover_min=0.50):
    """在墙上找**洞口**（纯几何，不依赖房间标签）。

    判据（缺一不可）：
      a) 空白段长度 ∈ [min_w, max_w]；
      b) 同一条扫描线上，空白段两侧都是墙（自动成立）；
      c) **局部墙体覆盖率**：以洞口为中心 ±win 范围内，这条扫描线上墙的占比
         必须 ≥ cover_min。这一条是关键 —— 没有它，一条只穿过上下两道横墙、
         中间整间是房间的竖线会被误判成 2.7m 的"大洞口"。
    """
    cands = []
    mn, mx = int(min_w * PP), int(max_w * PP)
    Wn = int(win * PP)

    def scan(line, coord, ori):
        segs = _runs(line)
        for a, b in zip(segs, segs[1:]):
            g0, g1 = a[1], b[0]
            if not (mn <= g1 - g0 <= mx):
                continue
            lo, hi = max(0, g0 - Wn), min(len(line), g1 + Wn)
            if (line[lo:hi] > 0).mean() < cover_min:
                continue
            cands.append([ori, coord, g0, g1])

    for r in range(0, H, 2):
        scan(wall[r] > 0, r, "h")
    for c in range(0, W, 2):
        scan(wall[:, c] > 0, c, "v")

    groups = []
    for ori, p, a0, a1, in sorted(cands, key=lambda t: (t[0], t[1], t[2])):
        for g in groups:
            if g["ori"] != ori or abs(g["p_last"] - p) > 6:
                continue
            ov = min(g["a1"], a1) - max(g["a0"], a0)
            if ov < 0.7 * min(g["a1"] - g["a0"], a1 - a0):
                continue
            g["ps"].append(p)
            g["a0"], g["a1"] = max(g["a0"], a0), min(g["a1"], a1)
            g["p_last"] = p
            break
        else:
            groups.append({"ori": ori, "ps": [p], "a0": a0, "a1": a1, "p_last": p})

    out = []
    for g in groups:
        if g["a1"] - g["a0"] < min_w * PP:
            continue
        p = float(np.median(g["ps"])) / PP
        a0, a1 = g["a0"] / PP, g["a1"] / PP
        seg = ([[round(a0, 3), round(p, 3)], [round(a1, 3), round(p, 3)]] if g["ori"] == "h"
               else [[round(p, 3), round(a0, 3)], [round(p, 3), round(a1, 3)]])
        out.append({"ori": g["ori"], "opening_m": seg, "width_m": round(a1 - a0, 3)})
    return out


def seal_gaps(gaps, like):
    """把洞口封成薄条，供分割房间使用。"""
    s = np.zeros_like(like)
    for g in gaps:
        a, b = np.array(g["opening_m"][0]), np.array(g["opening_m"][1])
        p0 = np.array([int(round(v * PP)) for v in a])
        p1 = np.array([int(round(v * PP)) for v in b])
        d = p1 - p0
        L = max(1.0, float(np.hypot(*d)))
        u = d / L
        nrm = np.array([-u[1], u[0]])
        half = int(round(0.06 * PP))
        for t in np.arange(0, L + 1, 2.0):
            c = p0 + u * t
            q0 = (c - nrm * half).astype(int)
            q1 = (c + nrm * half).astype(int)
            cv2.line(s, tuple(q0), tuple(q1), 255, max(2, int(0.05 * PP)))
        # 两端多探一点，确保和原有墙搭上
        for e in (-1, 1):
            c = p0 + u * (L if e > 0 else 0) + u * e * 0.05 * PP
            q0 = (c - nrm * half).astype(int)
            q1 = (c + nrm * half).astype(int)
            cv2.line(s, tuple(q0), tuple(q1), 255, max(2, int(0.05 * PP)))
    return cv2.dilate(s, np.ones((3, 3), np.uint8))


def main():
    from collections import Counter, defaultdict
    os.makedirs(os.path.join(DATA, "v5"), exist_ok=True)
    print("[1] 墙掩膜（轴向过滤，剔除 COLUWL-HATCH 的斜向填充线）")
    wall_raw, wall = stage_wall()
    cv2.imwrite(os.path.join(DATA, "v5", "wall_raw.png"), wall_raw)
    cv2.imwrite(os.path.join(DATA, "v5", "wall_solid.png"), wall)
    print(f"  墙面积 {int((wall>0).sum())/PP/PP:.2f} m2")

    print("[2] 门/玻璃/栏杆符号 + 几何洞口封堵")
    seal_raw, seal_sym = stage_seal()
    cv2.imwrite(os.path.join(DATA, "v5", "door_raw.png"), seal_raw)
    gaps = detect_gaps(wall)
    print(f"  几何洞口 {len(gaps)} 个: " +
          "、".join(f"{g['ori']}{g['width_m']:.2f}" for g in gaps))
    seal = cv2.bitwise_or(seal_sym, seal_gaps(gaps, wall))
    cv2.imwrite(os.path.join(DATA, "v5", "seal.png"), seal)

    print("[3] 房间分割（用旧房间集限定范围）")
    scope, old = build_scope(PP)
    lab, stats, cent, keep = stage_rooms(wall, seal, scope)
    info = name_components(lab, keep, old)

    # 同名碎片合并（同一房间被细线切断成两块）
    byname = defaultdict(list)
    for k in keep:
        byname[info[k]["name"]].append(k)
    merged = {}
    for nm, ks in byname.items():
        if nm in EXCLUDE_NAMES or nm == "未命名" or len(ks) == 1:
            for k in ks:
                merged[k] = k
            continue
        base = max(ks, key=lambda k: stats[k, cv2.CC_STAT_AREA])
        for k in ks:
            lab[lab == k] = base
            merged[k] = base
        print(f"  合并同名碎片: {nm} x{len(ks)}")
    keep = sorted(set(merged.values()))

    # 排除公摊
    kept = [k for k in keep if info[k]["name"] not in EXCLUDE_NAMES]
    dropped = [k for k in keep if info[k]["name"] in EXCLUDE_NAMES]
    print(f"  排除公摊 {len(dropped)} 间: {[info[k]['name'] for k in dropped]}")

    vis = np.zeros((H, W, 3), np.uint8)
    rng = np.random.default_rng(7)
    for k in kept:
        vis[lab == k] = rng.integers(90, 230, 3)
    vis[wall > 0] = (255, 255, 255)
    cv2.imwrite(os.path.join(DATA, "v5", "rooms_vis.png"), vis)
    np.save(os.path.join(DATA, "v5", "room_label.npy"), lab)

    print("[4] 房间矢量化（直角多边形）")
    rooms, room_of = [], {}
    kept_sorted = sorted(kept, key=lambda k: -np.count_nonzero(lab == k))
    for n, k in enumerate(kept_sorted):
        m = ((lab == k).astype(np.uint8)) * 255
        polys = mask_to_polys(m, ds=2, min_area=0.3)
        if not polys:
            print(f"    {info[k]['name']} 矢量化失败，跳过")
            continue
        p = max(polys, key=lambda g: g.area)
        rid = f"R{n}"
        room_of[k] = rid
        rooms.append({
            "id": rid, "name": info[k]["name"], "area_m2": round(p.area, 2),
            "polygon_m": [[round(x, 4), round(y, 4)] for x, y in p.exterior.coords],
            "holes_m": [[[round(x, 4), round(y, 4)] for x, y in r.coords] for r in p.interiors],
            "old_match": round(info[k]["match"], 2),
        })
    print(f"  {len(rooms)} 间: " + "、".join(f"{r['name']}{r['area_m2']}" for r in rooms))

    print("[5] 门窗识别（按图例分类）")
    door_raw = cv2.imread(os.path.join(DATA, "v5", "door_raw.png"), 0)
    doors, windows = [], []
    for i, op in enumerate(sorted(gaps, key=lambda g: -g["width_m"])):
        op = classify(op, door_raw, door_raw, lab, room_of)
        op["id"] = f"D{i}"
        op["hinge_m"] = op["opening_m"][0]
        op["leaf_m"] = op["width_m"]
        op["rooms"] = [r for r in op.pop("room_ids") if r]
        op["rooms"] = op.get("rooms") or []
        (windows if op["type"] == "window" else doors).append(op)
    print("  类型统计:", dict(Counter(d["type"] for d in doors + windows)))
    for d in doors + windows:
        print(f"    {d['id']:4s} {d['type']:8s} w={d['width_m']:.2f} {d['rooms']} "
              f"seg={d['opening_m']} perp={d['_perp']} dpx={d['_door_px']} gpx={d['_glass_px']}")

    print("[6] 写盘")
    wall_polys = mask_to_polys(wall, ds=2, min_area=0.05)
    walls_out = [{
        "shell": [[round(x, 4), round(y, 4)] for x, y in g.exterior.coords],
        "holes": [[[round(x, 4), round(y, 4)] for x, y in r.coords] for r in g.interiors],
    } for g in wall_polys]
    print(f"  墙多边形 {len(walls_out)} 段")

    allroom = unary_union([Polygon(r["polygon_m"]) for r in rooms])
    uid = unary_union([allroom, unary_union([Polygon(w["shell"], w["holes"]) for w in walls_out])])
    uid = max(list(uid.geoms) if uid.geom_type == "MultiPolygon" else [uid], key=lambda g: g.area)

    strip = lambda lst: [{k: v for k, v in d.items() if not k.startswith("_")} for d in lst]
    os.makedirs(APPDATA, exist_ok=True)
    json.dump(walls_out, open(os.path.join(APPDATA, "walls_poly.json"), "w", encoding="utf-8"))
    json.dump({"polygon_m": [[round(x, 4), round(y, 4)] for x, y in uid.exterior.coords]},
              open(os.path.join(APPDATA, "roof_poly.json"), "w", encoding="utf-8"))
    graph = {
        "rooms": [{k: v for k, v in r.items() if k != "holes_m"} for r in rooms],
        "doors": strip(doors),
        "windows": strip(windows),
        "checks": {"area_total_m2": round(sum(r["area_m2"] for r in rooms), 2),
                   "placed_area_m2": round(allroom.area, 2),
                   "n_rooms": len(rooms), "n_doors": len(doors)},
    }
    json.dump(graph, open(os.path.join(APPDATA, "room-graph.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"rooms": rooms, "doors": strip(doors), "windows": strip(windows)},
              open(os.path.join(DATA, "v5", "geom.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  walls_poly.json {len(walls_out)} 段 / room-graph.json {len(rooms)} 房间 "
          f"{len(doors)} 门 {len(windows)} 窗 / 套内 {graph['checks']['area_total_m2']} m2")
    print("DONE")


def _clean_ring(pts, eps=1e-6):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    # 去共线
    ch = True
    while ch and len(out) >= 4:
        ch = False
        n = len(out)
        for i in range(n):
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            if (abs(a[0] - b[0]) < eps and abs(b[0] - c[0]) < eps) or \
               (abs(a[1] - b[1]) < eps and abs(b[1] - c[1]) < eps):
                out.pop(i)
                ch = True
                break
    return out


def _ortho_ring(pts, eps=1e-9):
    """把 8-连通轮廓的「对角步」展开成两个轴向步 -> 严格直角多边形。

    ⚠️ 踩坑记录：房间 / 墙体多边形出现「非 90° 斜边」的真正来源是**矢量化的取轮廓环节**，
       而不是掩膜本身（栅格掩膜的边界天然是轴向的）：
         (1) cv2.findContours 的轮廓是 8-连通的，相邻点可能是 (±1,±1) 对角步；
         (2) CHAIN_APPROX_SIMPLE 会把一整段 45° 像素阶梯**压缩成一条 45° 斜线**
             （0.9m 长的阶梯就压成 0.9m 的长斜边）。
       这里把每条非轴向边（|dx|,|dy| 均非零）拆成「先水平、后垂直」的两段 L 形，
       配合调用方改用 CHAIN_APPROX_NONE，保证输出多边形严格正交。
    """
    out = []
    for p in pts:
        p = (float(p[0]), float(p[1]))
        if not out:
            out.append(p)
            continue
        a = out[-1]
        if abs(p[0] - a[0]) > eps and abs(p[1] - a[1]) > eps:
            out.append((p[0], a[1]))
        out.append(p)
    return out


def mask_to_polys(mask, ds=2, min_area=0.05):
    """二值掩膜 -> **严格直角**多边形（shapely）。ds: 下采样倍数（1 像素 = ds/PP 米）。"""
    h, w = mask.shape
    H2, W2 = h // ds, w // ds
    blk = mask[:H2 * ds, :W2 * ds].reshape(H2, ds, W2, ds).mean(axis=(1, 3)) >= 0.5
    m = (blk * 255).astype(np.uint8)
    # 3×3 开闭吃掉 1px 锯齿 / 凹口，让边界干净（方形小核不会磨出 45°，见 v6 的 envelope 注释）
    k3 = np.ones((3, 3), np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k3)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k3)
    # ⚠️ 必须用 NONE：SIMPLE 会把 45° 像素阶梯压成 45° 斜边（斜墙的根源）
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    def ring_of(c):
        pts = []
        for p in c[:, 0, :]:
            x = (p[0] + 0.5) * ds / PP
            y = (p[1] + 0.5) * ds / PP
            pts.append((round(x, 4), round(y, 4)))
        return _clean_ring(_ortho_ring(pts))
    polys = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:
            continue
        ext = ring_of(c)
        if len(ext) < 4:
            continue
        holes = []
        j = hier[i][2]
        while j != -1:
            if hier[j][3] == -1 or True:
                hr = ring_of(cnts[j])
                if len(hr) >= 4:
                    holes.append(hr)
            j = hier[j][0]
        try:
            p = Polygon(ext, holes)
            if not p.is_valid:
                p = p.buffer(0)
        except Exception:
            continue
        if p.is_empty:
            continue
        for g in (list(p.geoms) if p.geom_type == "MultiPolygon" else [p]):
            if g.area >= min_area:
                polys.append(g)
    return polys


if __name__ == "__main__":
    main()

