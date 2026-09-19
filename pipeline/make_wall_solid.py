"""
make_wall_solid.py — 从「双线墙」的闭合轮廓填实出**真实墙厚的实心墙**，
供 3D 墙带几何使用。

为什么要单独做：
  rooms_v4.py 里的 `close(wall, 61px)` 是**只给房间分割用的**（0.45m 大核用来堵门洞），
  它的产物被误用于 3D 墙带几何 -> 墙被膨胀 0.45m 并与邻近墙糊成一片，
  俯视图里房间地面被切成不规则形状。本脚本显式区分两套 mask。

原理：CAD 双线墙 = 两条平行线 + 两端封口 = 闭合的细长轮廓。
      findContours + 按层级填充（外轮廓 255、洞 0）即可得到真实厚度实心墙。
输出：data/wall_solid.png
"""
import os
import cv2
import numpy as np

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")

wall = cv2.imread(os.path.join(DATA, "mask_wall.png"), 0)
H, W = wall.shape

cnts, hier = cv2.findContours(wall, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
hier = hier[0] if hier is not None else []
print(f"contours={len(cnts)}")

solid = np.zeros((H, W), np.uint8)
MIN_AREA = 200          # 忽略极小碎轮廓
filled_outer = 0
for i, c in enumerate(cnts):
    a = cv2.contourArea(c)
    if a < MIN_AREA:
        continue
    is_outer = (hier[i][3] == -1)
    # 外轮廓填 255；嵌套洞填 0（恢复中空）
    cv2.drawContours(solid, [c], -1, 255 if is_outer else 0, cv2.FILLED)
    if is_outer:
        filled_outer += 1
print(f"filled outer contours: {filled_outer}")

# 闭合墙的微小断口（线线接头处的 1-2px 缝）用极小核补一下，不改变整体厚度
solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))

nz = int((solid > 0).sum())
print(f"wall pixels: raw={int((wall>0).sum())} solid={nz}  ({nz/(H*W)*100:.2f}%)")

cv2.imwrite(os.path.join(DATA, "wall_solid.png"), solid)

# 对比图：原墙线(灰) + 填实墙(半透明红)
vis = cv2.cvtColor(wall, cv2.COLOR_GRAY2BGR)
vis[solid > 0] = (0, 0, 180)
cv2.imwrite(os.path.join(DATA, "wall_solid_check.png"), vis)
print("WROTE data/wall_solid.png + wall_solid_check.png")
