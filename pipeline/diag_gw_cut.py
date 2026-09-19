"""diag_gw_cut.py — 公卫区域「被切」诊断。

把 barrier（墙∪封堵条）与 room_label 在公卫 ROI 上放大重绘：
  灰 = 结构墙(P-WALL 等)  红 = 洞口封堵条  彩色 = 房间连通域
这样能一眼看出是哪一条封堵条把公卫切开的。
"""
import os, sys, json
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geom_v5 as G5

ROOT = os.path.join(HERE, "..")
V6 = os.path.join(ROOT, "data", "v6")
PP, W, H = G5.PP, G5.W, G5.H

X0, Y0, X1, Y1 = 9.9, 1.3, 12.4, 4.9
SCALE = 3.0


def main():
    wall = cv2.imread(os.path.join(V6, "wall.png"), 0)
    seal = cv2.imread(os.path.join(V6, "seal_inst.png"), 0)
    sealg = cv2.imread(os.path.join(V6, "seal_gaps.png"), 0)
    lab = np.load(os.path.join(V6, "room_label.npy"))

    h, w = int((Y1 - Y0) * PP), int((X1 - X0) * PP)
    x0, y0 = int(X0 * PP), int(Y0 * PP)
    roi = lambda a: a[y0:y0 + h, x0:x0 + w]

    wall_r, seal_r, sealg_r, lab_r = roi(wall), roi(seal), roi(sealg), roi(lab)

    canvas = np.full((h, w, 3), 255, np.uint8)
    # 房间连通域着色
    ids = [i for i in np.unique(lab_r) if i != 0]
    rng = np.random.default_rng(11)
    cols = {i: tuple(int(v) for v in rng.integers(120, 245, 3)) for i in ids}
    for i in ids:
        canvas[lab_r == i] = cols[i]
    # 结构墙 = 深灰；封堵条 = 红 / 橙
    canvas[wall_r > 0] = (110, 110, 110)
    canvas[sealg_r > 0] = (0, 165, 255)
    canvas[seal_r > 0] = (30, 30, 230)

    big = cv2.resize(canvas, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_NEAREST)

    # 网格 + 标注
    def px(x, y):
        return (int((x - X0) * PP * SCALE), int((y - Y0) * PP * SCALE))

    yy = math_floor(Y0, 0.25)
    while yy <= Y1:
        p0, p1 = px(X0, yy), px(X1, yy)
        cv2.line(big, p0, p1, (200, 200, 200), 1)
        cv2.putText(big, f"{yy:g}", (4, p1[1] - 3), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (120, 120, 120), 1)
        yy = round(yy + 0.25, 4)
    xx = math_floor(X0, 0.25)
    while xx <= X1:
        p0, p1 = px(xx, Y0), px(xx, Y1)
        cv2.line(big, p0, p1, (200, 200, 200), 1)
        cv2.putText(big, f"{xx:g}", (p0[0] + 2, 12), cv2.FONT_HERSHEY_SIMPLEX,
                    0.35, (120, 120, 120), 1)
        xx = round(xx + 0.25, 4)

    # 关键水平线
    for yv, tag, col in [(1.59, "y=1.59", (0, 0, 200)), (2.16, "y=2.16", (0, 0, 200)),
                         (2.62, "y=2.62", (0, 0, 200)), (3.47, "y=3.47", (0, 0, 200)),
                         (3.51, "y=3.51", (150, 0, 150)), (3.67, "y=3.67", (0, 140, 0)),
                         (4.52, "y=4.52", (0, 140, 0))]:
        p0, p1 = px(X0, yv), px(X1, yv)
        cv2.line(big, p0, p1, col, 1, cv2.LINE_4)
        cv2.putText(big, tag, (p1[0] - 62, p1[1] - 3), cv2.FONT_HERSHEY_SIMPLEX,
                    0.38, col, 1)

    outp = os.path.join(V6, "diag_gw_cut.png")
    cv2.imwrite(outp, big)
    print("SAVED", outp, big.shape)
    print("ROI 内连通域:", ids, "面积(m2):",
          {int(i): round(int((lab_r == i).sum()) / PP / PP, 2) for i in ids})


def math_floor(v, q):
    import math
    return math.floor(v / q) * q


if __name__ == "__main__":
    main()
