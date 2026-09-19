"""make_plan2.py — 修正版平面图（方向对齐 PDF，y 向下）。
在淡化的 PDF 原图上，叠加「修正后的我的理解」：
  - 补上主卧套间内的 女衣帽间 / 男衣帽间
  - 主卧入口门 D11 翻转 180°（门轴移到东端，向南开）
  - 玻璃移门按「固定扇/移动扇」绘制
中文用 PIL 绘制。
用法: python pipeline/make_plan2.py [full|master]
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
    "R0": "客餐厅厨房", "R1": "主卧", "R2": "小孩房", "R3": "客厅阳台",
    "R4": "书房", "R5": "衣帽间(瑶瑶)", "R6": "主卫", "R7": "小孩房阳台",
    "R8": "次卫", "R9": "主卧飘窗", "R10": "小孩房飘窗", "R11": "公卫(厨房旁)",
}
# 主卧衣帽间 = 一个整体空间（男/女只是后期用柜体分隔，不是两间、不是两道门）
EXTRA_ROOMS = [
    ("主卧衣帽间", [(6.85, 10.95), (11.00, 10.95), (11.00, 12.22), (6.85, 12.22)]),
]
CLOSET_CABINET_X = (8.55, 9.44)          # PDF 里的 X 交叉柜体（男/女分界）
CLOSET_ZONE_LABELS = [("女衣帽间", 7.75, 11.80), ("男衣帽间", 9.95, 11.80)]
# 主卧入口门：门轴移到东端（翻转 180°），向南开
D11_FIX = {"hinge": [11.815, 12.225], "open": [[10.905, 12.225], [11.815, 12.225]], "swing": -1}
# 衣帽间南侧 = 一整道 3 扇玻璃移门（跨 7.40~10.45）
#   PDF 把中段 8.55~9.44 画得像墙，其实那是「中间固定扇」
CLOSET_SLIDER_Y = 12.22
CLOSET_SLIDER_PANELS = [
    (7.40, 8.55, False),    # 左：可移动
    (8.55, 9.44, True),     # 中：固定
    (9.44, 10.45, False),   # 右：可移动
]
# 各类移门的扇型配置
SLIDING_CFG = {
    "D0": {"n": 4, "fixed": [1, 2]},   # 客厅阳台
    "D5": {"n": 4, "fixed": [1, 2]},   # 小孩房阳台
    "D8": {"n": 2, "fixed": [0]},      # 厨房阳台（一固定一移动）
}

mode = sys.argv[1] if len(sys.argv) > 1 else "full"
if mode == "master":
    X0, Y0, X1, Y1, PP = 4.2, 9.4, 13.2, 17.5, 110.0
elif mode == "closet":
    X0, Y0, X1, Y1, PP = 6.2, 10.25, 11.75, 13.25, 180.0
else:
    X0, Y0, X1, Y1, PP = 6.0, 1.0, 18.6, 17.5, 95.0

doc = pymupdf.open(PDF)
pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(PP / PT_PER_M, PP / PT_PER_M),
                        colorspace=pymupdf.csRGB, alpha=False)
base = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
base = cv2.cvtColor(base, cv2.COLOR_RGB2BGR)
base = cv2.addWeighted(base, 0.38, np.full_like(base, 255), 0.62, 0)

img = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB)).convert("RGB")
d = ImageDraw.Draw(img)
F  = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
FS = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)

def P(x, y): return (x * PP, y * PP)

# ---- 房间 ----
def room_poly(pts, fill, outline, label, lab_col=(150, 0, 0)):
    pp = [P(x, y) for x, y in pts]
    if fill is not None:
        d.polygon(pp, fill=fill)
    d.line(pp + [pp[0]], fill=outline, width=3, joint="curve")
    cx = sum(p[0] for p in pp) / len(pp); cy = sum(p[1] for p in pp) / len(pp)
    d.text((cx, cy), label, fill=lab_col, font=F, anchor="mm",
           stroke_width=3, stroke_fill=(255, 255, 255))

for r in g["rooms"]:
    room_poly(r["polygon_m"], None, (220, 70, 70),
              ROOM_LABEL.get(r["id"], r["name"]))
for nm, pts in EXTRA_ROOMS:
    room_poly(pts, None, (230, 130, 30), nm, (170, 80, 0))
for nm, lx, ly in CLOSET_ZONE_LABELS:
    d.text(P(lx, ly), nm, fill=(150, 95, 20), font=FS, anchor="mm",
           stroke_width=3, stroke_fill=(255, 255, 255))
_c0, _c1 = CLOSET_CABINET_X
d.rectangle([P(_c0, 11.02), P(_c1, 12.05)], outline=(150, 150, 150), width=2)
d.text(P((_c0 + _c1) / 2, 11.14), "柜体", fill=(125, 125, 125), font=FS, anchor="mm",
       stroke_width=3, stroke_fill=(255, 255, 255))

# ---- 墙（橙）----
for b in walls:
    pts = [P(p[0], p[1]) for p in b["shell"]]
    d.line(pts + [pts[0]], fill=(235, 120, 0), width=3)

# ---- 平开门 ----
def draw_swing(hinge, opening, sign=+1, dashed=True):
    hx, hy = P(*hinge)
    ox, oy = P(*opening)
    r = math.hypot(ox - hx, oy - hy)
    a0 = math.degrees(math.atan2(oy - hy, ox - hx))
    # PIL: 角度自 3 点钟起顺时针（屏幕坐标 y 向下）
    if sign >= 0:
        d.arc([hx - r, hy - r, hx + r, hy + r], a0, a0 + 90, fill=(60, 120, 60), width=2)
    else:
        d.arc([hx - r, hy - r, hx + r, hy + r], a0 - 90, a0, fill=(60, 120, 60), width=2)
    d.line([(hx, hy), (ox, oy)], fill=(40, 150, 40), width=4)

def draw_slider(a, b, cfg):
    ax, ay = P(*a); bx, by = P(*b)
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    n = cfg["n"]; pw = L / n
    for i in range(n):
        cx, cy = ax + ux * pw * (i + 0.5), ay + uy * pw * (i + 0.5)
        off = 5 if i not in cfg["fixed"] else -5
        px, py = cx + nx * off, cy + ny * off
        hw, hh = pw / 2 - 1, 8
        quad = [(px - ux * hw - nx * hh, py - uy * hw - ny * hh),
                (px + ux * hw + nx * hh, py + uy * hw + ny * hh),
                (px + ux * hw - nx * hh, py + uy * hw - ny * hh),
                (px - ux * hw + nx * hh, py - uy * hw + ny * hh)]
        col = (90, 170, 205) if i in cfg["fixed"] else (200, 235, 245)
        d.polygon(quad, fill=col, outline=(60, 140, 180))

for dd in g["doors"]:
    if dd["id"] == "D11":
        draw_swing(D11_FIX["hinge"], D11_FIX["open"][0], D11_FIX["swing"])
        mx, my = P(11.36, 12.225)
        d.text((mx, my - 16), "主卧门(已翻转)", fill=(0, 110, 0), font=FS, anchor="mm",
               stroke_width=3, stroke_fill=(255, 255, 255))
    elif dd["type"] == "swing":
        o = dd["opening_m"]; h = dd["hinge_m"]
        other = o[1] if (abs(h[0] - o[0][0]) < 1e-6 and abs(h[1] - o[0][1]) < 1e-6) else o[0]
        draw_swing(h, other, +1)
    else:
        o = dd["opening_m"]
        cfg = SLIDING_CFG.get(dd["id"], {"n": 2, "fixed": [0]})
        draw_slider(o[0], o[1], cfg)
        mx, my = P((o[0][0] + o[1][0]) / 2, (o[0][1] + o[1][1]) / 2)
        d.text((mx, my - 16), dd["id"] + " 玻璃移门", fill=(0, 110, 160), font=FS, anchor="mm",
               stroke_width=3, stroke_fill=(255, 255, 255))

# 衣帽间南侧：一整道 3 扇玻璃移门（中固定 / 左右移动）
for _x0, _x1, _fixed in CLOSET_SLIDER_PANELS:
    draw_slider((_x0, CLOSET_SLIDER_Y), (_x1, CLOSET_SLIDER_Y),
                {"n": 1, "fixed": [0] if _fixed else []})
    d.text(P((_x0 + _x1) / 2, CLOSET_SLIDER_Y - 0.17), "固定扇" if _fixed else "可移动",
           fill=(130, 60, 0) if _fixed else (0, 110, 160), font=FS, anchor="mm",
           stroke_width=3, stroke_fill=(255, 255, 255))
d.text(P(6.95, 12.62), "衣帽间玻璃移门：一整道 3 扇 · 中间固定 / 左右两扇可移动",
       fill=(0, 110, 160), font=FS, anchor="lm",
       stroke_width=3, stroke_fill=(255, 255, 255))

# ---- 窗（洋红）----
for w in g.get("windows", []):
    o = w["opening_m"]
    d.line([P(*o[0]), P(*o[1])], fill=(190, 0, 190), width=4)

# ---- 裁剪 ----
x0, y0 = P(X0, Y0); x1, y1 = P(X1, Y1)
img = img.crop((max(0, int(x0)), max(0, int(y0)),
                min(img.width, int(x1)), min(img.height, int(y1))))

bar = Image.new("RGB", (img.width, 58), "white")
bd = ImageDraw.Draw(bar)
bd.text((8, 6), "修正版平面图 v3：红=房间  橙=墙  绿=平开门(弧线=开向)  蓝=玻璃移门(实心=固定扇)",
        fill=(0, 0, 0), font=FS)
bd.text((8, 32), "主卧衣帽间=一个整体空间（男/女仅柜体分隔）；南侧为一整道 3 扇玻璃移门（中固定·左右移动）；主卧入口门已翻转 180°",
        fill=(170, 0, 0), font=FS)
out = Image.new("RGB", (img.width, img.height + 58), "white")
out.paste(bar, (0, 0)); out.paste(img, (0, 58))

fn = f"{ROOT}/data/v6/plan_v2_{mode}.png"
out.save(fn); print("SAVED", fn, out.size)
