"""查询指定米制矩形内的所有矢量元素，按图层分组打印 —— 用于确认「图例」含义。

用法: python pipeline/probe_region.py mx0 my0 mx1 my1 [--dump]
"""
import os, sys, json
import collections

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PT_PER_M = 45.36

mx0, my0, mx1, my1 = (float(v) for v in sys.argv[1:5])
dump = "--dump" in sys.argv
x0, y0, x1, y1 = mx0 * PT_PER_M, my0 * PT_PER_M, mx1 * PT_PER_M, my1 * PT_PER_M

layers = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

def bbox_of(it):
    xs = [p[0] for p in it["pts"]]
    ys = [p[1] for p in it["pts"]]
    return min(xs), min(ys), max(xs), max(ys)

hit = collections.defaultdict(list)
for ln, items in layers.items():
    for it in items:
        try:
            bx0, by0, bx1, by1 = bbox_of(it)
        except Exception:
            continue
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        hit[ln].append(it)

print(f"=== 区域 m({mx0},{my0})-({mx1},{my1}) ===")
for ln in sorted(hit, key=lambda k: -len(hit[k])):
    items = hit[ln]
    cols = collections.Counter(it["color"] for it in items)
    print(f"\n--- {ln}  命中 {len(items)} 个  colors={dict(cols)}")
    # 按 bbox 聚类后输出
    if dump:
        for it in items[:60]:
            bx = bbox_of(it)
            m = tuple(round(v / PT_PER_M, 2) for v in bx)
            print(f"    {it['kind']:5s} n={len(it['pts']):2d} bbox_m={m} w={it.get('width'):.2f}")
            print(f"        pts={[[round(p[0]/PT_PER_M,2), round(p[1]/PT_PER_M,2)] for p in it['pts']][:6]}")
