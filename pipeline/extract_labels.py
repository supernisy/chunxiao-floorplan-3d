"""
extract_labels.py — 提取 CAD 矢量文字（P-TEXT 填充图元）的 bbox，按行聚类成
标签块，并高清渲染成一张网格对照图，供肉眼读取「文字内容↔坐标」。
因为文字是矢量轮廓，get_text() 取不到，但 bbox 位置是确定的。
输出：data/labels.json、data/labels_grid.png、data/labels_overlay.png
"""
import os, json
import fitz
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")

doc = fitz.open(PDF)
page = doc[0]

# 1) 收集 P-TEXT 图元矩形
items = []
for d in page.get_drawings():
    lay = d.get("layer") or ""
    if "P-TEXT" not in lay:
        continue
    r = d["rect"]
    if r.width <= 0 or r.height <= 0:
        continue
    items.append((r.x0, r.y0, r.x1, r.y1))
print("P-TEXT fill rects:", len(items))

# 2) 行聚类：按 y 中心排序分组
items.sort(key=lambda t: ((t[1] + t[3]) / 2, t[0]))
rows = []
for it in items:
    yc = (it[1] + it[3]) / 2
    h = it[3] - it[1]
    placed = False
    for row in rows:
        ry = row["yc"]
        if abs(yc - ry) < max(h, row["h"]) * 0.6:
            row["items"].append(it)
            n = len(row["items"])
            row["yc"] = (row["yc"] * (n - 1) + yc) / n
            row["h"] = max(row["h"], h)
            placed = True
            break
    if not placed:
        rows.append({"yc": yc, "h": h, "items": [it]})
print("rows:", len(rows))

# 3) 行内按 x 分段成标签（间距 > 2pt 断开）
labels = []
for row in rows:
    row["items"].sort(key=lambda t: t[0])
    cur = []
    for it in row["items"]:
        if not cur:
            cur = [it]
        else:
            gap = it[0] - max(c[2] for c in cur)
            if gap > 2.2:
                labels.append(cur)
                cur = [it]
            else:
                cur.append(it)
    if cur:
        labels.append(cur)

out = []
for i, grp in enumerate(labels):
    x0 = min(c[0] for c in grp); y0 = min(c[1] for c in grp)
    x1 = max(c[2] for c in grp); y1 = max(c[3] for c in grp)
    n = len(grp)
    # 单字太小的丢弃（噪声）
    if n == 1 and (x1 - x0) < 3.5:
        continue
    out.append({"id": len(out), "nchars": n,
                "bbox_pt": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                "center_pt": [round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)]})
print("labels:", len(out))
json.dump(out, open(os.path.join(DATA, "labels.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# 4) 渲染网格对照图：每个标签裁剪 + 8x 放大
ZOOM = 8.0
PAD = 1.5
cell_h = 46
cols = 6
cell_w = 210
rows_n = (len(out) + cols - 1) // cols
grid = np.full((rows_n * cell_h + 10, cols * cell_w + 10, 3), 255, np.uint8)
for k, lab in enumerate(out):
    x0, y0, x1, y1 = lab["bbox_pt"]
    clip = fitz.Rect(x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD)
    pm = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip, colorspace=fitz.csRGB)
    img = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, 3).copy()
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    # 适配 cell
    sc = min((cell_w - 46) / img.shape[1], (cell_h - 8) / img.shape[0])
    if sc < 1:
        img = cv2.resize(img, (max(1, int(img.shape[1] * sc)), max(1, int(img.shape[0] * sc))),
                         interpolation=cv2.INTER_AREA)
    r, c = k // cols, k % cols
    oy = r * cell_h + 10 + (cell_h - 8 - img.shape[0]) // 2
    ox = c * cell_w + 10 + 42
    h, w = img.shape[:2]
    if oy + h <= grid.shape[0] and ox + w <= grid.shape[1]:
        grid[oy:oy + h, ox:ox + w] = img
    cv2.putText(grid, f"#{k}", (c * cell_w + 12, r * cell_h + 10 + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.line(grid, (c * cell_w + 10, r * cell_h + 10), (c * cell_w + 10, r * cell_h + cell_h + 10),
             (200, 200, 200), 1)
cv2.imwrite(os.path.join(DATA, "labels_grid.png"), grid)
print("WROTE labels_grid.png", grid.shape)

# 5) 叠加图：在原色渲染上画标签框+编号
base = fitz.open(PDF)[0].get_pixmap(matrix=fitz.Matrix(3, 3), colorspace=fitz.csRGB)
ov = np.frombuffer(base.samples, np.uint8).reshape(base.height, base.width, 3).copy()
ov = cv2.cvtColor(ov, cv2.COLOR_RGB2BGR)
for lab in out:
    x0, y0, x1, y1 = [int(v * 3) for v in lab["bbox_pt"]]
    cv2.rectangle(ov, (x0 - 2, y0 - 2), (x1 + 2, y1 + 2), (0, 0, 255), 1)
    cv2.putText(ov, str(lab["id"]), (x0, y0 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
cv2.imwrite(os.path.join(DATA, "labels_overlay.png"), ov)
print("WROTE labels_overlay.png", ov.shape)
