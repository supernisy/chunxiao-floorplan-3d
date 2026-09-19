"""probe_region2.py — 列出 ROI（米）内所有矢量图元：图层 / 颜色 / 几何。

用法: python pipeline/probe_region2.py X0 Y0 X1 Y1 [--all]

默认每组（图层+颜色+kind）最多打 12 条；传 --all 取消上限并让每个图元完整展开——
排查"某段墙到底有没有画"这类问题时必须用 --all，否则关键图元会被截掉。
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geom_v5 as G5

PT = 45.36
MAX_SHOW = 12


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_all = "--all" in sys.argv
    cap = 10 ** 9 if show_all else MAX_SHOW
    x0, y0, x1, y1 = (float(v) for v in args[:4])

    def inroi(p):
        mx, my = p[0] / PT, p[1] / PT
        return x0 <= mx <= x1 and y0 <= my <= y1

    hits = {}
    for name, items in G5.LAYERS.items():
        for it in items:
            pts = it.get("pts") or []
            if not pts:
                continue
            sel = [p for p in pts if inroi(p)]
            if not sel:
                continue
            hits.setdefault((name, (it.get("color") or "").upper(), it.get("kind")), []).append(
                [(round(p[0] / PT, 3), round(p[1] / PT, 3)) for p in sel])

    for (name, col, kind), groups in sorted(hits.items(), key=lambda t: -len(t[1])):
        print(f"\n=== {name}  {col}  kind={kind}  共 {len(groups)} 个图元")
        for gpts in groups[:cap]:
            if len(gpts) <= 6:
                print("   ", gpts)
            else:
                print(f"    pts={len(gpts)}  x[{min(p[0] for p in gpts):.2f},"
                      f"{max(p[0] for p in gpts):.2f}] y[{min(p[1] for p in gpts):.2f},"
                      f"{max(p[1] for p in gpts):.2f}]")
        if len(groups) > cap:
            print(f"    ... 另有 {len(groups)-cap} 个（加 --all 看全）")


if __name__ == "__main__":
    main()
