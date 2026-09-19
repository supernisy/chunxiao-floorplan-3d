# -*- coding: utf-8 -*-
"""只渲染指定图层组，用于判读洁具/门窗等符号（避免墙线干扰）。
用法: python pipeline/layer_only.py <x0> <y0> <x1> <y1> <out.png> [ppm]
"""
import sys, math, collections
import numpy as np, cv2, pymupdf

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
PT = 45.36

GROUPS = [
    (("P-TOILET",),                                   (0, 170, 170), "洁具 P-TOILET"),
    (("P-DOOR",),                                     (0, 100, 255), "门 P-DOOR"),
    (("A-通-门窗剖线", "COMM-GLAZ-SECT"),              (60, 60, 200), "窗/玻璃剖线"),
    (("A-平-楼梯", "FLOR-STAIR", "栏杆扶手", "FLOR-RAIL"), (30, 160, 30), "楼梯/栏杆"),
    (("P-EQU", "COMM-EQPM", "空调设备"),               (140, 140, 140), "设备"),
]


def main():
    x0, y0, x1, y1 = map(float, sys.argv[1:5])
    out = sys.argv[5]
    ppm = float(sys.argv[6]) if len(sys.argv) > 6 else 420.0
    doc = pymupdf.open(ROOT + r"\assets\chunxiao.pdf")
    pg = doc[0]
    clip = pymupdf.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT)
    W, H = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
    canvas = np.full((H, W, 3), 255, np.uint8)

    def P(pt):
        return (int((pt.x / PT - x0) * ppm), int((pt.y / PT - y0) * ppm))

    counts = collections.Counter()
    for pats, col, lab in GROUPS:
        n = 0
        for d in pg.get_drawings():
            lay = str(d.get("layer") or "")
            if not any(p in lay for p in pats):
                continue
            if d["rect"].x0 > clip.x1 or d["rect"].x1 < clip.x0 or d["rect"].y0 > clip.y1 or d["rect"].y1 < clip.y0:
                continue
            n += 1
            for it in d["items"]:
                t = it[0]
                if t == "l":
                    cv2.line(canvas, P(it[1]), P(it[2]), col, 2)
                elif t == "re":
                    r = it[1]
                    cv2.rectangle(canvas, P(pymupdf.Point(r.x0, r.y0)), P(pymupdf.Point(r.x1, r.y1)), col, 2)
                elif t == "qu":
                    q = it[1]
                    pts = np.array([P(q.ul), P(q.ur), P(q.lr), P(q.ll)], np.int32)
                    cv2.polylines(canvas, [pts], True, col, 2)
                elif t == "c":
                    p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                    prev = P(p1)
                    for s in np.linspace(0, 1, 24):
                        x = (1 - s) ** 3 * p1.x + 3 * (1 - s) ** 2 * s * p2.x + 3 * (1 - s) * s * s * p3.x + s ** 3 * p4.x
                        y = (1 - s) ** 3 * p1.y + 3 * (1 - s) ** 2 * s * p2.y + 3 * (1 - s) * s * s * p3.y + s ** 3 * p4.y
                        cur = P(pymupdf.Point(x, y))
                        cv2.line(canvas, prev, cur, col, 2)
                        prev = cur
        counts[lab] = n

    # 网格 0.25m
    g = math.ceil(x0 / 0.25) * 0.25
    while g < x1:
        px = int((g - x0) * ppm); major = abs(g - round(g)) < 1e-6
        cv2.line(canvas, (px, 0), (px, H), (0, 0, 235) if major else (238, 238, 250), 1)
        if major:
            cv2.putText(canvas, f"{g:g}", (px + 1, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 180), 1)
        g += 0.25
    g = math.ceil(y0 / 0.25) * 0.25
    while g < y1:
        py = int((g - y0) * ppm); major = abs(g - round(g)) < 1e-6
        cv2.line(canvas, (0, py), (W, py), (0, 0, 235) if major else (238, 238, 250), 1)
        if major:
            cv2.putText(canvas, f"{g:g}", (1, py + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 0, 180), 1)
        g += 0.25

    # 左上角图例
    y = 26
    for _, col, lab in GROUPS:
        cv2.line(canvas, (10, y - 4), (34, y - 4), col, 3)
        txt = f"{lab}  n={counts[lab]}"
        cv2.putText(canvas, txt.encode("ascii", "replace").decode(), (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        y += 22
    cv2.imwrite(out, canvas)
    print("SAVED", out, canvas.shape, dict(counts))


if __name__ == "__main__":
    main()
