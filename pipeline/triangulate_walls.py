"""
triangulate_walls.py — 用 Shewchuk CDT（triangle 库）把墙带三角化，输出**三角形网格**
给前端直接渲染，彻底绕开 three.js 的 earcut。

为什么必须绕开 earcut：
  earcut 在「极瘦的凹多边形」上会因浮点精度产出跨越整个多边形的退化三角形
  （俯视图里的大片尖刺）。CDT 是工业级算法，对这类输入稳健。

第二次过滤（本脚本的关键）：
  ⚠️ 踩坑记录：曾试图按「高/底 < 0.10」剔除退化细长三角，结果把**墙主体**
     一起删了 —— 墙体是 3m×0.2m 的细长条，其 CDT 三角形天然长宽比 ~15:1。
     结论：CDT 对细长多边形本就稳健，**不做长宽比过滤**，只剔除近零面积三角。

输入：app/src/data/walls_poly.json（export_data.py 产出的、已裁剪到套内）
输出：app/src/data/walls_tri.json  {bands:[{vertices,triangles}], height_m}
     data/walls_tri_check.png    2D 验证图
"""
import json, os
import numpy as np
import triangle as tr
import cv2
from shapely.geometry import Polygon

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "app", "src", "data")

SRC = os.path.join(OUT, "walls_poly.json")          # 裁剪 + 清理后的墙带
walls = json.load(open(SRC, encoding="utf-8"))
print(f"input bands: {len(walls)}")

SLIM_RATIO = 0.0          # 0 = 关闭长宽比过滤（见下方说明）
MIN_AREA = 1e-6           # 只剔除近乎零面积的退化三角（单位 m^2）
bands_out = []
n_total = n_kept = 0

def clean_ring(ring):
    """去掉相邻重复点与首尾重复点。
    ⚠️ 踩坑记录：v6 的 walls_poly.json 每个环末尾都复写了首点（闭环冗余），
       产生零长度 segment，会让 Shewchuk CDT 直接 segfault（exit 139，无任何输出）。
       这里统一清洗成严格首尾不重合的简单环。"""
    out = []
    for p in ring:
        q = [float(p[0]), float(p[1])]
        if out and abs(out[-1][0] - q[0]) < 1e-9 and abs(out[-1][1] - q[1]) < 1e-9:
            continue
        out.append(q)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) < 1e-9 and abs(out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


for idx, w in enumerate(walls):
    shell = clean_ring(w["shell"])
    holes = [clean_ring(h) for h in w.get("holes", [])]
    holes = [h for h in holes if len(h) >= 3]
    if len(shell) < 3:
        print(f"  band#{idx}: shell too small, skipped")
        continue

    verts, segs, hole_pts = [], [], []

    def add_ring(ring):
        base = len(verts)
        for p in ring:
            verts.append([float(p[0]), float(p[1])])
        n = len(ring)
        for k in range(n):
            segs.append([base + k, base + (k + 1) % n])
        return base

    add_ring(shell)
    for h in holes:
        add_ring(h)
        try:
            c = Polygon(h).representative_point()
            hole_pts.append([c.x, c.y])
        except Exception:
            hole_pts.append(list(np.mean(h, axis=0)))

    data = {"vertices": np.array(verts, float), "segments": np.array(segs, np.int32)}
    if hole_pts:
        data["holes"] = np.array(hole_pts, float)

    try:
        res = tr.triangulate(data, "pQ")
    except Exception as e:
        print(f"  band#{idx} CDT FAILED: {e}")
        continue

    tv, tt = res["vertices"], res["triangles"]
    keep = []
    for (i, j, k) in tt:
        p, q, r = tv[i], tv[j], tv[k]
        e = [np.hypot(*(q - p)), np.hypot(*(r - q)), np.hypot(*(p - r))]
        L = max(e)
        if L < 1e-9:
            continue
        area2 = abs((q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1]))
        if area2 * 0.5 < MIN_AREA:              # 面积近零 -> 真退化，剔除
            continue
        if SLIM_RATIO > 0 and (area2 / L) / L < SLIM_RATIO:
            # 仅在显式开启时按长宽比过滤。
            # ⚠️ 默认关闭：墙体本身是 3m×0.2m 的细长条，其 CDT 三角形天然
            #    长宽比 ~15:1，用长宽比过滤会把**墙主体**一起删掉（实测只剩边缘碎片）。
            continue
        keep.append([int(i), int(j), int(k)])

    n_total += len(tt)
    n_kept += len(keep)
    if not keep:
        print(f"  band#{idx}: all triangles slim, skipped")
        continue
    bands_out.append({
        "vertices": [[round(float(p[0]), 4), round(float(p[1]), 4)] for p in tv],
        "triangles": keep,
    })
    print(f"  band#{idx}: tris {len(tt)} -> {len(keep)}")

json.dump({"bands": bands_out, "height_m": 2.9},
          open(os.path.join(OUT, "walls_tri.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(f"WROTE walls_tri.json  bands={len(bands_out)}  "
      f"tris {n_total} -> {n_kept} (剔除细长 {n_total - n_kept})")

# ---- 2D 验证 ----
S = 60.0
allp = np.vstack([np.array(b["vertices"], float) for b in bands_out]) if bands_out else np.zeros((1, 2))
mn, mx = allp.min(axis=0) - 0.5, allp.max(axis=0) + 0.5
img = np.full((int((mx[1] - mn[1]) * S), int((mx[0] - mn[0]) * S), 3), 255, np.uint8)


def px(p):
    return (int((p[0] - mn[0]) * S), int((p[1] - mn[1]) * S))


for b in bands_out:
    v = b["vertices"]
    for (i, j, k) in b["triangles"]:
        cv2.fillPoly(img, [np.array([px(v[i]), px(v[j]), px(v[k])], np.int32)], (140, 140, 140))
cv2.imwrite(os.path.join(DATA, "walls_tri_check.png"), img)
print("WROTE data/walls_tri_check.png", img.shape)
