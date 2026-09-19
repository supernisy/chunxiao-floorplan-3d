"""把 labels.json 里的文字块逐个裁图，拼成带编号的接触表，一次读全。

用法: python pipeline/label_sheet.py [cols] [zoom] [mx0 my0 mx1 my1]
后 4 个参数（单位米）可选，用于只导出某个区域内的标注。
"""
import os, sys, json
import numpy as np
import cv2
import pymupdf as fitz

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M = 45.36

cols = int(sys.argv[1]) if len(sys.argv) > 1 else 6
zoom = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
region = [float(v) for v in sys.argv[3:7]] if len(sys.argv) > 6 else None

labels = json.load(open(os.path.join(DATA, "labels.json"), encoding="utf-8"))
if region:
    rx0, ry0, rx1, ry1 = region
    labels = [lb for lb in labels
              if rx0 <= lb["center_pt"][0] / PT_PER_M <= rx1 and ry0 <= lb["center_pt"][1] / PT_PER_M <= ry1]
    labels = [dict(lb, id=str(lb["id"])) for lb in labels]
doc = fitz.open(PDF)
page = doc[0]

TW, TH = 190.0, 46.0        # 每格 pt 尺寸
tw, th = int(TW * zoom), int(TH * zoom)
rows = (len(labels) + cols - 1) // cols
sheet = np.full((rows * (th + 22), cols * tw, 3), 255, np.uint8)

for k, lb in enumerate(labels):
    x0, y0, x1, y1 = lb["bbox_pt"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = fitz.Rect(cx - TW / 2, cy - TH / 2, cx + TW / 2, cy + TH / 2)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=r)
    tile = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    rr, cc = divmod(k, cols)
    ry, rx = rr * (th + 22), cc * tw
    tile = tile[:th, :tw]
    sheet[ry:ry + tile.shape[0], rx:rx + tile.shape[1]] = tile
    cv2.rectangle(sheet, (rx, ry), (rx + tw - 1, ry + tile.shape[0] - 1), (0, 0, 255), 1)
    cap = f"#{k} ({cx/PT_PER_M:.2f},{cy/PT_PER_M:.2f})m"
    cv2.putText(sheet, cap, (rx + 2, ry + th + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (0, 0, 200), 1, cv2.LINE_AA)

out = os.path.join(DATA, "label_sheet.png")
cv2.imwrite(out, sheet)
print("SAVED", out, sheet.shape, "labels:", len(labels))
