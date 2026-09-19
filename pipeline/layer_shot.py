"""layer_shot.py — 按图层组渲染 PDF 局部，用来看清"骨架/洁具/门窗"。

用法:
  python pipeline/layer_shot.py <group> <out.png> <x0> <y0> <x1> <y1> [ppm] [grid_m]
group: wall | fixture | doorwin | text | all
坐标单位: 米（原点=PDF 左上，y 向下）
"""
import sys
import numpy as np, cv2, pymupdf

PT_PER_M = 45.36
PDF = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25/assets/chunxiao.pdf"

GROUPS = {
    "wall": ["P-WALL", "P-WALL FIN", "A-通-墙", "S-柱墙-模板线", "S-柱墙-填充", "COLUWL"],
    "fixture": ["P-TOILET", "P-FURNITURE", "I-FURNITURE", "FLOR-FURN", "洁"],
    "doorwin": ["P-DOOR", "COMM-GLAZ-SECT", "FLOR-RAIL", "FLOR-STAIR"],
}
GROUPS["all"] = GROUPS["wall"] + GROUPS["fixture"] + GROUPS["doorwin"]


def main():
    a = sys.argv[1:]
    group = a[0]
    out = a[1]
    x0, y0, x1, y1 = (float(v) for v in a[2:6])
    ppm = float(a[6]) if len(a) > 6 else 220.0
    grid = float(a[7]) if len(a) > 7 else 0.5
    pats = GROUPS[group]

    doc = pymupdf.open(PDF)
    pg = doc[0]
    W, H = int((x1 - x0) * ppm) + 1, int((y1 - y0) * ppm) + 1
    canvas = np.full((H, W, 3), 255, np.uint8)

    def P(x, y):
        return (int((x - x0) * ppm), int((y - y0) * ppm))

    for d in pg.get_drawings():
        lay = str(d.get("layer"))
        if not any(p in lay for p in pats):
            continue
        col = d.get("color")
        if col is not None:
            b, g, r = [int(round(c * 255)) for c in col]
        else:
            b = g = r = 0
        for it in d["items"]:
            t = it[0]
            if t == "l":
                cv2.line(canvas, P(it[1].x / PT_PER_M, it[1].y / PT_PER_M),
                         P(it[2].x / PT_PER_M, it[2].y / PT_PER_M), (b, g, r), 1)
            elif t == "re":
                rc = it[1]
                cv2.rectangle(canvas, P(rc.x0 / PT_PER_M, rc.y0 / PT_PER_M),
                              P(rc.x1 / PT_PER_M, rc.y1 / PT_PER_M), (b, g, r), 1)
            elif t == "qu":
                q = it[1]
                pts = np.array([P(q.ul.x / PT_PER_M, q.ul.y / PT_PER_M),
                                P(q.ur.x / PT_PER_M, q.ur.y / PT_PER_M),
                                P(q.lr.x / PT_PER_M, q.lr.y / PT_PER_M),
                                P(q.ll.x / PT_PER_M, q.ll.y / PT_PER_M)])
                cv2.polylines(canvas, [pts], True, (b, g, r), 1)
            elif t == "c":
                p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                prev = P(p1.x / PT_PER_M, p1.y / PT_PER_M)
                for s in np.linspace(0, 1, 12):
                    xx = ((1 - s) ** 3 * p1.x + 3 * (1 - s) ** 2 * s * p2.x
                          + 3 * (1 - s) * s * s * p3.x + s ** 3 * p4.x) / PT_PER_M
                    yy = ((1 - s) ** 3 * p1.y + 3 * (1 - s) ** 2 * s * p2.y
                          + 3 * (1 - s) * s * s * p3.y + s ** 3 * p4.y) / PT_PER_M
                    cur = P(xx, yy)
                    cv2.line(canvas, prev, cur, (b, g, r), 1)
                    prev = cur

    # 网格
    if grid > 0:
        import math
        gx = math.ceil(x0 / grid) * grid
        while gx < x1:
            px = int((gx - x0) * ppm)
            cv2.line(canvas, (px, 0), (px, H), (0, 0, 235), 1)
            cv2.putText(canvas, f"{gx:g}", (px + 2, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 180), 1)
            gx += grid
        gy = math.ceil(y0 / grid) * grid
        while gy < y1:
            py = int((gy - y0) * ppm)
            cv2.line(canvas, (0, py), (W, py), (0, 0, 235), 1)
            cv2.putText(canvas, f"{gy:g}", (2, py + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 180), 1)
            gy += grid

    if W > 1500:
        s = 1500.0 / W
        canvas = cv2.resize(canvas, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, canvas)
    print("SAVED", out, canvas.shape)


main()
