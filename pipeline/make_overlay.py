"""make_overlay.py — 把「我的理解」直接叠到 PDF 原图上（同一坐标系，y 向下）。
方向与 PDF 完全一致，可直接对照。中文用 PIL 绘制。
用法:
  python pipeline/make_overlay.py full
  python pipeline/make_overlay.py master
"""
import json, math, sys
import numpy as np, cv2, pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
PT_PER_M = 45.36
PDF = f"{ROOT}/assets/chunxiao.pdf"
g = json.load(open(f"{ROOT}/app/src/data/room-graph.json", encoding="utf-8"))
walls = json.load(open(f"{ROOT}/app/src/data/walls_poly.json", encoding="utf-8"))

ROOM_LABEL = {
    "R0": "客餐厅厨房", "R1": "主卧套间", "R2": "小孩房", "R3": "客厅阳台",
    "R4": "书房", "R5": "衣帽间(瑶瑶)", "R6": "主卫", "R7": "小孩房阳台",
    "R8": "次卫", "R9": "主卧飘窗", "R10": "小孩房飘窗", "R11": "公卫(厨房旁)",
}

mode = sys.argv[1] if len(sys.argv) > 1 else "full"
if mode == "master":
    X0, Y0, X1, Y1, PP = 4.2, 9.4, 13.2, 17.5, 110.0
else:
    X0, Y0, X1, Y1, PP = 6.0, 1.0, 18.6, 17.5, 95.0

doc = pymupdf.open(PDF)
pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(PP / PT_PER_M, PP / PT_PER_M),
                        colorspace=pymupdf.csRGB, alpha=False)
base = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
base = cv2.cvtColor(base, cv2.COLOR_RGB2BGR).copy()
base = cv2.addWeighted(base, 0.40, np.full_like(base, 255), 0.60, 0)

# 画布（全页 -> PIL）
img = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB))
d = ImageDraw.Draw(img)
FT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
FS = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)

def P(x, y):
    return ((x) * PP, (y) * PP)

# 房间（红）
for r in g["rooms"]:
    pts = [P(p[0], p[1]) for p in r["polygon_m"]]
    d.polygon(pts, outline=(220, 50, 50), width=3)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    lab = ROOM_LABEL.get(r["id"], r["name"])
    d.text((cx, cy), lab, fill=(180, 0, 0), font=FT, anchor="mm",
           stroke_width=2, stroke_fill=(255, 255, 255))

# 墙（橙蓝）
for b in walls:
    pts = [P(p[0], p[1]) for p in b["shell"]]
    d.line(pts + [pts[0]], fill=(230, 90, 0), width=2)
    for h in b.get("holes", []):
        hp = [P(p[0], p[1]) for p in h]
        d.line(hp + [hp[0]], fill=(230, 90, 0), width=1)

# 门
for dd in g["doors"]:
    o = dd["opening_m"]; a, b = o[0], o[1]
    pa, pb = P(a[0], a[1]), P(b[0], b[1])
    col = (0, 160, 0) if dd["type"] == "swing" else (220, 170, 0)
    d.line([pa, pb], fill=col, width=4)
    h = dd.get("hinge_m")
    if h:
        hx, hy = P(h[0], h[1])
        d.ellipse([hx - 5, hy - 5, hx + 5, hy + 5], fill=col)
    d.text(((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), dd["id"],
           fill=col, font=FS, anchor="ms", stroke_width=2, stroke_fill=(255, 255, 255))

# 窗（洋红）
for w in g.get("windows", []):
    o = w["opening_m"]; a, b = o[0], o[1]
    pa, pb = P(a[0], a[1]), P(b[0], b[1])
    d.line([pa, pb], fill=(200, 0, 200), width=4)
    d.text(((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), w["id"],
           fill=(200, 0, 200), font=FS, anchor="ms", stroke_width=2, stroke_fill=(255, 255, 255))

# 裁剪
x0, y0 = P(X0, Y0); x1, y1 = P(X1, Y1)
x0, y0 = max(0, int(x0)), max(0, int(y0))
x1, y1 = min(img.width, int(x1)), min(img.height, int(y1))
img = img.crop((x0, y0, x1, y1))

# 说明条
bar = Image.new("RGB", (img.width, 56), "white")
bd = ImageDraw.Draw(bar)
bd.text((8, 6), "PDF原图(淡化) + 我的理解：红=房间  橙=墙  绿=平开门  黄=移门  洋红=窗",
        fill=(0, 0, 0), font=FS)
bd.text((8, 30), "方向已与 PDF 一致（y 向下，北=图上方）", fill=(180, 0, 0), font=FS)
out = Image.new("RGB", (img.width, img.height + 56), "white")
out.paste(bar, (0, 0))
out.paste(img, (0, 56))

fn = f"{ROOT}/data/v6/overlay_{mode}.png"
out.save(fn)
print("SAVED", fn, out.size)
