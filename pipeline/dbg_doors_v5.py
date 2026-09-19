"""dbg_doors_v5.py — 诊断 v5 门识别：洞口窗口里到底有没有门像素、房间标签对不对。"""
import os, sys, json, math
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, cv2
import geom_v5 as G

wall = cv2.imread(os.path.join(G.DATA, "v5", "wall_solid.png"), 0)
door = cv2.imread(os.path.join(G.DATA, "v5", "door_raw.png"), 0)
lab = np.load(os.path.join(G.DATA, "v5", "room_label.npy"))

gaps = G.detect_gaps(wall)
print(f"洞口 {len(gaps)}")
for i, op in enumerate(sorted(gaps, key=lambda g: -g["width_m"])):
    a, b = op["opening_m"]
    P = int(round(0.30 * G.PP))
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    lx, ly = int(round(mid[0] * G.PP)), int(round(mid[1] * G.PP))
    if op["ori"] == "h":
        la = lab[max(0, ly - P), lx]; lb = lab[min(G.H - 1, ly + P), lx]
        cv2.circle(wall, (lx, ly - P), 5, 200, -1)
        cv2.circle(wall, (lx, ly + P), 5, 200, -1)
    else:
        la = lab[ly, max(0, lx - P)]; lb = lab[ly, min(G.W - 1, lx + P)]
        cv2.circle(wall, (lx - P, ly), 5, 200, -1)
        cv2.circle(wall, (lx + P, ly), 5, 200, -1)

    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    if op["ori"] == "h":
        x0 -= 0.05; x1 += 0.05; y0 -= 0.45; y1 += 0.45
    else:
        y0 -= 0.05; y1 += 0.05; x0 -= 0.45; x1 += 0.45
    px0, py0 = int(max(0, x0 * G.PP)), int(max(0, y0 * G.PP))
    px1, py1 = int(min(G.W, x1 * G.PP)), int(min(G.H, y1 * G.PP))
    nd = int((door[py0:py1, px0:px1] > 0).sum())
    # 更大窗口再数一次（1.0m 半径），看是否只是窗口太小
    bx0, by0 = int(max(0, (x0 - 0.5) * G.PP)), int(max(0, (y0 - 0.5) * G.PP))
    bx1, by1 = int(min(G.W, (x1 + 0.5) * G.PP)), int(min(G.H, (y1 + 0.5) * G.PP))
    nd_big = int((door[by0:by1, bx0:bx1] > 0).sum())
    print(f"D{i:<3d} {op['ori']} w={op['width_m']:.2f} mid=({mid[0]:.2f},{mid[1]:.2f}) "
          f"lab=({la},{lb}) win=[{px0},{py0},{px1},{py1}] "
          f"nd={nd} nd_big={nd_big} wallpx={int((wall[py0:py1,px0:px1]>0).sum())}")

cv2.imwrite(os.path.join(G.DATA, "v5", "dbg_gap_probe.png"), wall)
print("写 data/v5/dbg_gap_probe.png")
