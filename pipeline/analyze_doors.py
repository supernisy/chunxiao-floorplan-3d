"""analyze_doors.py — 分析 P-DOOR / COMM-GLAZ-SECT 图元几何，定位门扇线与门弧。"""
import json, os, math
from collections import Counter

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
layers = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))
S = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
PT_PER_M = S["points_per_meter"]
print(f"PT_PER_M = {PT_PER_M:.3f}  (1m = {PT_PER_M:.1f}pt)")

for lname in ["P-DOOR", "A-通-门窗剖线.....COMM-GLAZ-SECT"]:
    ds = layers[lname]
    print(f"\n=== {lname} : {len(ds)} items ===")
    print("  by kind:", dict(Counter(d["kind"] for d in ds)))
    print("  by color:", dict(Counter(d["color"] for d in ds)))

    lines = []
    for d in ds:
        if d["kind"] == "line":
            (x0, y0), (x1, y1) = d["pts"][0], d["pts"][1]
            L = math.hypot(x1 - x0, y1 - y0)
            lines.append((L, (x0, y0), (x1, y1), d["color"]))
    if lines:
        Ls = sorted(l[0] for l in lines)
        n = len(Ls)
        q = lambda p: Ls[min(n - 1, int(p * n))]
        print(f"  line lengths (pt): min={Ls[0]:.2f} p25={q(.25):.2f} med={q(.5):.2f} p75={q(.75):.2f} p90={q(.9):.2f} max={Ls[-1]:.2f}")
        print(f"  line lengths (m):  min={Ls[0]/PT_PER_M:.2f} med={q(.5)/PT_PER_M:.2f} max={Ls[-1]/PT_PER_M:.2f}")

    curves = [d for d in ds if d["kind"] == "curve"]
    if curves:
        npts = [len(c["pts"]) for c in curves]
        print(f"  curves={len(curves)} pts_per_curve min={min(npts)} max={max(npts)} med={sorted(npts)[len(npts)//2]}")
        # 试着对第一条估半径
        c = curves[0]["pts"]
        xs = [p[0] for p in c]; ys = [p[1] for p in c]
        print(f"    curve0 bbox=({min(xs):.2f},{min(ys):.2f})-({max(xs):.2f},{max(ys):.2f}) npts={len(c)}")

# 门扇候选：P-DOOR 中长度 0.6~1.2m 的 line
print("\n=== P-DOOR long-ish lines (0.6m < L < 1.4m) ===")
cands = []
for d in layers["P-DOOR"]:
    if d["kind"] != "line":
        continue
    (x0, y0), (x1, y1) = d["pts"][0], d["pts"][1]
    L = math.hypot(x1 - x0, y1 - y0) / PT_PER_M
    if 0.6 < L < 1.4:
        cands.append((round(L, 3), (round(x0, 1), round(y0, 1)), (round(x1, 1), round(y1, 1)), d["color"]))
print(f"count={len(cands)}")
for c in sorted(cands, key=lambda t: -t[0])[:40]:
    print("  ", c)
