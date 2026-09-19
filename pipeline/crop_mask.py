"""把若干掩膜按同一米制矩形裁出并横排对照，用于判定各颜色图元的归属。

用法: python pipeline/crop_mask.py mx0 my0 mx1 my1 out.png mask1.png mask2.png ...
掩膜按 PP=200 px/m、原点=PDF 原点 的约定解释。
"""
import os, sys
import numpy as np
import cv2

HERE = os.path.dirname(__file__)
DATA = os.path.join(os.path.dirname(HERE), "data")
PP = 200.0

mx0, my0, mx1, my1 = (float(v) for v in sys.argv[1:5])
out_name = sys.argv[5]
names = sys.argv[6:]

x0, y0 = int(mx0 * PP), int(my0 * PP)
x1, y1 = int(mx1 * PP), int(my1 * PP)

tiles = []
for n in names:
    p = n if os.path.isabs(n) else os.path.join(DATA, n)
    img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if img is None:
        print("MISSING", p)
        continue
    crop = img[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0:
        print("EMPTY crop", n)
        continue
    bgr = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
    # 缩到统一高度便于横排
    tiles.append((os.path.splitext(os.path.basename(n))[0], crop))

if not tiles:
    sys.exit("no tiles")

TH = 1100
scaled = []
for name, t in tiles:
    s = TH / t.shape[0]
    r = cv2.resize(t, (max(1, int(t.shape[1] * s)), TH), interpolation=cv2.INTER_NEAREST)
    r = cv2.cvtColor(r, cv2.COLOR_GRAY2BGR)
    cv2.putText(r, name[:28], (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA)
    scaled.append(r)

sheet = np.hstack([np.hstack([s, np.full((TH, 8, 3), 60, np.uint8)]) for s in scaled])
out = os.path.join(DATA, out_name)
cv2.imwrite(out, sheet)
print("SAVED", out, sheet.shape, "tiles:", [n for n, _ in tiles])
