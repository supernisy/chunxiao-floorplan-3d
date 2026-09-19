"""在掩膜上叠加米制网格 + 可选矢量轮廓，便于读坐标核对。

用法: python pipeline/view_mask.py src.png out.png mx0 my0 mx1 my1 [scale] [grid]
"""
import os, sys
import numpy as np
import cv2

HERE = os.path.dirname(__file__)
ROOT = os.path.join(os.path.dirname(HERE), "data")
PP = 200.0

src, out = sys.argv[1], sys.argv[2]
mx0, my0, mx1, my1 = (float(v) for v in sys.argv[3:7])
scale = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
grid = float(sys.argv[8]) if len(sys.argv) > 8 else 0.5

img = cv2.imread(src if os.path.isabs(src) else os.path.join(ROOT, src), cv2.IMREAD_GRAYSCALE)
if img is None:
    sys.exit("missing " + src)
x0, y0, x1, y1 = [int(v * PP) for v in (mx0, my0, mx1, my1)]
c = img[y0:y1, x0:x1].copy()
if scale != 1.0:
    c = cv2.resize(c, (int(c.shape[1] * scale), int(c.shape[0] * scale)), interpolation=cv2.INTER_NEAREST)
vis = cv2.cvtColor(c, cv2.COLOR_GRAY2BGR)

ppm = PP * scale
gx = np.floor(mx0 / grid) * grid
while gx <= mx1 + 1e-9:
    px = int(round((gx - mx0) * ppm))
    major = abs(gx / 1.0 - round(gx / 1.0)) < 1e-6
    cv2.line(vis, (px, 0), (px, vis.shape[0]), (0, 0, 255) if major else (0, 90, 90), 2 if major else 1)
    if major:
        cv2.putText(vis, f"{gx:.0f}", (px + 3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1, cv2.LINE_AA)
    gx += grid
gy = np.floor(my0 / grid) * grid
while gy <= my1 + 1e-9:
    py = int(round((gy - my0) * ppm))
    major = abs(gy / 1.0 - round(gy / 1.0)) < 1e-6
    cv2.line(vis, (0, py), (vis.shape[1], py), (0, 0, 255) if major else (0, 90, 90), 2 if major else 1)
    if major:
        cv2.putText(vis, f"{gy:.0f}", (4, py - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1, cv2.LINE_AA)
    gy += grid

outp = out if os.path.isabs(out) else os.path.join(ROOT, out)
cv2.imwrite(outp, vis)
print("SAVED", outp, vis.shape)
