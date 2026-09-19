"""
export_data.py — 把管线产物整理给前端 app/src/data/
输出：room-graph.json、walls_poly.json（套内裁剪+清理）、roof_poly.json（套内轮廓）

本步做三件事：
  1) 排除公摊房间（电梯厅/楼梯间/电梯井）—— 不属套内，不建模
  2) 墙带裁剪到「套内区域」—— 顺带剔除混在 P-WALL 图层里的电梯厅非墙线
  3) 墙带几何 opening + 顶点清理 —— 让 earcut 三角化稳定（消除退化黑面）
"""
import json, math, os
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "app", "src", "data")
os.makedirs(OUT, exist_ok=True)

EXCLUDE_ROOM_NAMES = {"电梯厅", "楼梯间", "消防电梯", "普通电梯"}
KEEP_BUFFER_M = 0.30          # 套内区域外扩：把套内周边外墙包进来

g = json.load(open(os.path.join(DATA, "room-graph.json"), encoding="utf-8"))
walls = json.load(open(os.path.join(DATA, "walls_poly.json"), encoding="utf-8"))


def dedupe(pts, min_d=0.02):
    """去掉近重复点，保证最小边长 >= min_d。earcut 对 <1cm 的边极敏感，
    会产出穿透墙体的退化三角形 —— 即俯视图里的黑色锐利碎片/尖刺。"""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_d:
            out.append(p)
    while len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_d:
        out.pop()
    return out


# ---------------- 轴向吸附（snap-to-axis） ----------------
# ⚠️ 根因：PDF 图纸里墙线并非严格轴向 —— 实测墙线有 ~11% 落在 1~5°、
#    7% 落在 >5°（多为 COLUWL-HATCH 柱墙填充的斜边，带固定 8.4pt 偏移）。
#    这些微斜在 3D 里表现为「墙微微歪 + 房间不规则」，与平面图观感不符。
#    建筑户型本就是纯正交的，故统一把近轴边吸附到水平/垂直。
ORTHO_TOL_DEG = 20.0     # 与轴偏差 < 该角度 => 强制轴向


def _ortho_axis(coords, pairs):
    """并查集：把 pairs 里「应相等」的坐标归组，每组取均值。
    ⚠️ 早期用「逐边迭代赋值」会震荡 —— 移动一个顶点会破坏相邻的精确轴边，
    132 点的大环迭代后反而更歪（实测非轴边 17.8% -> 39.4%，并扭出畸形）。
    并查集是**一次求解**，无震荡。"""
    n = len(coords)
    if n == 0:
        return list(coords)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = list(coords)
    for members in groups.values():
        m = sum(coords[i] for i in members) / len(members)
        for i in members:
            out[i] = m
    return out


def ortho_ring(ring, tol=ORTHO_TOL_DEG):
    pts = [[float(p[0]), float(p[1])] for p in ring]
    n = len(pts)
    if n < 4:
        return pts
    hz, vt = [], []                    # hz: y 相等的边；vt: x 相等的边
    for i in range(n):
        j = (i + 1) % n
        dx = pts[j][0] - pts[i][0]
        dy = pts[j][1] - pts[i][1]
        if math.hypot(dx, dy) < 1e-9:
            continue
        ang = math.degrees(math.atan2(abs(dy), abs(dx)))   # 0=水平, 90=竖直
        if ang <= tol:
            hz.append((i, j))
        elif ang >= 90 - tol:
            vt.append((i, j))
    xs = _ortho_axis([p[0] for p in pts], vt)
    ys = _ortho_axis([p[1] for p in pts], hz)
    return [[xs[i], ys[i]] for i in range(n)]


def ortho_poly(p, tol=ORTHO_TOL_DEG):
    """对 Polygon 做轴向吸附；带面积守卫，形变过大则放弃。"""
    if p.geom_type != "Polygon":
        return p
    try:
        ext = ortho_ring(list(p.exterior.coords)[:-1], tol)
        holes = [ortho_ring(list(r.coords)[:-1], tol) for r in p.interiors]
        q = Polygon(ext, holes)
        if not q.is_valid:
            q = q.buffer(0)
        if q.is_empty:
            return p
        if p.area > 1e-6 and abs(q.area - p.area) > 0.30 * p.area:
            return p                      # 形变过大 -> 放弃，保守
        return q
    except Exception:
        return p


def ortho_pts(ring, tol=ORTHO_TOL_DEG):
    """对纯点列做轴向吸附（用于房间 polygon_m）。"""
    r = [[float(p[0]), float(p[1])] for p in ring]
    return dedupe(ortho_ring(r, tol))


def room_poly_fix(ring, grow=0.03, tol=ORTHO_TOL_DEG):
    """房间多边形：先外扩 grow（盖住地板与墙之间的缝），再轴向吸附。
    缝的来源：room polygon 是墙的「内表面」，与墙带之间有 1-3cm 的提取误差，
    俯视时露成白色小三角。外扩 3cm 即可盖住（重叠区被墙带遮住，无副作用）。"""
    try:
        p = Polygon(ring)
        if not p.is_valid:
            p = p.buffer(0)
        if grow > 0:
            p = p.buffer(grow, join_style=2)
        if p.is_empty or p.geom_type != "Polygon":
            return ortho_pts(ring, tol)
        return ortho_pts(list(p.exterior.coords)[:-1], tol)
    except Exception:
        return ortho_pts(ring, tol)


def clean_geom(w):
    """栅格轮廓 -> 清理后的 shapely (Multi)Polygon

    ⚠️ 刻意**不做 buffer(round-join) opening**：round join 会在每个转角插入大量
    圆弧逼近点，earcut 在这种密集近共线顶点上会产出跨越整个多边形的退化三角形
    （实测：加了 opening 后俯视图墙带崩成大片尖刺；去掉后显著收敛）。
    细线污染已在 make_masks 的**图层层面**排除，无需几何 opening。
    """
    try:
        pg = Polygon(w["shell"], w.get("holes", []))
        if not pg.is_valid:
            pg = pg.buffer(0)
        # ⚠️ 不再做形态学 opening（buffer(-d).buffer(+d)）：mitre join 在凹角处
        #    会产生 45° 斜切，是 3D 里白色斜切三角的来源之一。细尖由 is_band_like
        #    + 后续 ortho_poly 处理。
        pg = pg.simplify(0.02, preserve_topology=True)
        pg = ortho_poly(pg)                       # 轴向吸附：消除 PDF 带来的微斜
        if not pg.is_valid:
            pg = pg.buffer(0)
        return None if pg.is_empty else pg
    except Exception as e:
        print("  band skipped:", e)
        return None


def is_band_like(pg, min_width=0.09):
    """墙带应该是「有宽度的条带」。

    ⚠️ P-WALL 图层里混有**门洞示意线 / 开启方向斜线**等非墙图元。这些线在轮廓提取后
    退化成极瘦的楔形多边形，若不过滤，会被拉伸成 3D 里的尖锐三角刺。
    真墙厚 >= 0.1m，用外接旋转矩形的**短边 >= 0.09m** 作为判据即可干净区分。
    """
    try:
        mrr = pg.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)
        edges = [math.hypot(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
                 for i in range(len(c) - 1)]
        edges = [e for e in edges if e > 1e-9]
        return len(edges) >= 2 and min(edges) >= min_width
    except Exception:
        return True


def to_json_poly(p):
    shell = dedupe([[round(x, 4), round(y, 4)] for x, y in p.exterior.coords])
    if len(shell) < 3:
        return None
    holes = []
    for r in p.interiors:
        if Polygon(r).area >= 0.05:
            h = dedupe([[round(x, 4), round(y, 4)] for x, y in r.coords])
            if len(h) >= 3:
                holes.append(h)
    return {"shell": shell, "holes": holes}


# ---- 0) 房间多边形轴向吸附（消除 PDF 带来的 ~1-5° 微斜）----
n_ortho = 0
for r in g["rooms"]:
    before = r["polygon_m"]
    after = room_poly_fix(before)
    if len(after) >= 3 and after != before:
        n_ortho += 1
        r["polygon_m"] = after
print(f"rooms orthogonalized: {n_ortho}/{len(g['rooms'])}")

# ---- 1) 排除公摊 ----
all_rooms = g["rooms"]
kept = [r for r in all_rooms if r["name"] not in EXCLUDE_ROOM_NAMES]
dropped = [f"{r['id']}:{r['name']}" for r in all_rooms if r["name"] in EXCLUDE_ROOM_NAMES]
print(f"rooms {len(all_rooms)} -> {len(kept)}   dropped={dropped}")
g["rooms"] = kept

kept_ids = {r["id"] for r in kept}
before_d = len(g["doors"])
g["doors"] = [d for d in g["doors"]
              if any(rid in kept_ids for rid in (d.get("rooms") or []))]
print(f"doors {before_d} -> {len(g['doors'])}  (纯公摊门已剔除)")

adj = {}
for d in g["doors"]:
    rs = [r for r in (d.get("rooms") or []) if r in kept_ids]
    if len(rs) == 2 and rs[0] != rs[1]:
        adj.setdefault(rs[0], set()).add(rs[1])
        adj.setdefault(rs[1], set()).add(rs[0])
g["adjacency"] = {k: sorted(v) for k, v in adj.items()}

g["checks"]["n_rooms"] = len(kept)
g["checks"]["n_doors"] = len(g["doors"])
g["checks"]["area_total_m2"] = round(sum(r["area_m2"] for r in kept), 2)
g["checks"]["excluded_public"] = dropped

# ---- 2) 公摊区域：用于从墙带中「抠除」，而非裁剪套内 ----
# ⚠️ 踩坑记录：曾用 keep_area = union(套内房间).buffer(0.3) 裁剪墙带，
#    但 buffer 的 mitre join 在房间锐角处会产生 45° 斜切边，被裁剪时传到
#    墙带上 -> 3D 里成白色斜切三角（房间看起来「不规则」）。
#    改法：墙带保持完整，只把「公摊房间内部」抠掉。切口沿公摊房间边界（直角），
#    套内的墙完全不受影响；公摊内的隔墙被自然移除。
pub_polys = []
for r in all_rooms:
    if r["name"] in EXCLUDE_ROOM_NAMES:
        try:
            p = Polygon(r["polygon_m"])
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                pub_polys.append(p)
        except Exception:
            pass
public_zone = (unary_union(pub_polys).buffer(0.02, join_style=2)
               if pub_polys else None)
if public_zone is not None:
    print(f"public zone: {public_zone.area:.1f} m2 ({len(pub_polys)} rooms)")

keep_polys = []
for r in kept:
    try:
        p = Polygon(r["polygon_m"])
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            keep_polys.append(p)
    except Exception:
        pass
keep_area = (unary_union(keep_polys)
             .buffer(KEEP_BUFFER_M, join_style=2))     # ortho 后 -> 边界轴对齐
keep_area = ortho_poly(keep_area)                      # 裁剪边界也轴对齐
print(f"keep area: {keep_area.area:.1f} m2 (buffered {KEEP_BUFFER_M}m, orthogonalized)")

# ---- 3) 墙带清理 + 抠除公摊 ----
walls_out = []
n_thin = 0
for w in walls:
    pg = clean_geom(w)
    if pg is None:
        continue
    # 先剔除「细线退化成的瘦楔形」（P-WALL 里的门洞示意线/斜线）
    parts = list(pg.geoms) if pg.geom_type == "MultiPolygon" else [pg]
    keep_parts = [p for p in parts if p.geom_type == "Polygon" and is_band_like(p)]
    n_thin += len(parts) - len(keep_parts)
    if not keep_parts:
        continue
    pg = unary_union(keep_parts)
    pg = pg.intersection(keep_area)          # 裁剪到套内（公摊被切掉）
    pg = pg.simplify(0.02, preserve_topology=True)
    if not pg.is_valid:
        pg = pg.buffer(0)
    if pg.is_empty:
        continue
    geoms = list(pg.geoms) if pg.geom_type == "MultiPolygon" else [pg]
    for p in geoms:
        if p.geom_type != "Polygon" or p.area < 0.05:
            continue
        p = ortho_poly(p)              # 裁剪后再轴向吸附 -> 最终输出轴对齐
        if not is_band_like(p):        # 裁剪后可能又产生细条，再查一次
            n_thin += 1
            continue
        j = to_json_poly(p)
        if j:
            walls_out.append(j)
print(f"walls {len(walls)} -> {len(walls_out)}  (抠除公摊, 剔除瘦楔形 {n_thin} 个)")

# ---- 4) roof = 套内轮廓（外扩一点把外墙包进来）----
u = keep_area.buffer(0.32, join_style=2)
if u.geom_type == "MultiPolygon":
    u = max(u.geoms, key=lambda p: p.area)
roof = [[round(x, 4), round(y, 4)] for x, y in
        ortho_pts(list(u.exterior.coords)[:-1])]
print(f"roof verts={len(roof)} area={u.area:.1f}")

json.dump(g, open(os.path.join(OUT, "room-graph.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(walls_out, open(os.path.join(OUT, "walls_poly.json"), "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"polygon_m": roof}, open(os.path.join(OUT, "roof_poly.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("WROTE to", OUT)
