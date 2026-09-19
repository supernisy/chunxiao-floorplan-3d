"""make_plan6.py — 理解平面图 v6：**直接画 pipeline 产出的数据**，不再手工重画。

与 v5（make_plan5.py）的区别
────────────────────────────────────────────────────────────────
1. 门开向直接读 room-graph.json 的 `door.side`（由 P-DOOR **橙色门扇质心**判读）。
   v5 用的是「PDF 开启弧现场推」，那把衣帽间门、主卫门判反了（用户已纠正）；
   门扇法自动给出「内开」，不需人工覆盖。
2. 公卫按数据实际轮廓画（L 形，东北角被管井占据），并标三进动线。
3. 飘窗读 `room.bays`（已并入所属房间），画成「0.5m 抬高台面」。
4. **每个房间标注数据 id**（R0/R1…），便于与实际图纸/我的提问逐条对照 ——
   之前提问不写清是哪张图的哪个编号，是沟通成本的主要来源。

用法: python pipeline/make_plan6.py [full|master|gw]
"""
import json, math, sys
import numpy as np, cv2, pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
PT_PER_M = 45.36
PDF = f"{ROOT}/assets/chunxiao.pdf"
g = json.load(open(f"{ROOT}/app/src/data/room-graph.json", encoding="utf-8"))

# 公卫三进标注（用户裁定：淋浴 → 马桶 → 盥洗；洗手台在马桶正南、贴东墙）
GW_NOTES = [
    ((10.80, 2.10), "①淋浴间", (0, 110, 40)),
    ((10.82, 3.02), "②马桶间", (0, 110, 40)),
    ((11.55, 4.08), "③盥洗龛", (0, 110, 40)),
]
GW_FLOW = ((10.42, 4.72), "公卫动线：客厅 → 盥洗龛(干区) → 门 → 马桶间 → 玻璃移门 → 淋浴间")

# 旧编号（v5 版数据）对照框：(x0, y0, x1, y1), 注记
OLD_ID_NOTE = [
    ((11.94, 16.18, 14.49, 17.04), "旧编号 R10 ← 上次问的就是这一处"),
    ((7.23, 16.20, 10.90, 17.03), "旧编号 R9"),
]

mode = sys.argv[1] if len(sys.argv) > 1 else "full"
if mode == "master":
    X0, Y0, X1, Y1, PP = 4.2, 9.4, 13.2, 17.8, 110.0
elif mode == "gw":
    X0, Y0, X1, Y1, PP = 9.7, 1.2, 12.6, 5.0, 245.0
else:
    X0, Y0, X1, Y1, PP = 6.0, 1.0, 18.6, 17.8, 95.0

doc = pymupdf.open(PDF)
pg = doc[0]
pix = pg.get_pixmap(matrix=pymupdf.Matrix(PP / PT_PER_M, PP / PT_PER_M),
                    colorspace=pymupdf.csRGB, alpha=False)
base = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n),
                    cv2.COLOR_RGB2BGR)
base = cv2.addWeighted(base, 0.30, np.full_like(base, 255), 0.70, 0)
img = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB)).convert("RGB")
d = ImageDraw.Draw(img)


def font(sz):
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", sz)


F, FS, FT = font(24), font(17), font(14)


def P(x, y):
    return (x * PP, y * PP)


def outline(pts, color, w=3, dash=False):
    pp = [P(x, y) for x, y in pts] + [P(*pts[0])]
    if not dash:
        d.line(pp, fill=color, width=w, joint="curve")
        return
    for i in range(len(pp) - 1):
        x0, y0 = pp[i]
        x1, y1 = pp[i + 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(seg / 12))
        for k in range(n):
            if k % 2:
                continue
            t0, t1 = k / n, (k + 0.75) / n
            d.line([(x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0),
                    (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1)], fill=color, width=w)


def label(x, y, text, color=(150, 0, 0), f=None, stroke=3, anchor="mm"):
    d.text(P(x, y), text, fill=color, font=f or F, anchor=anchor,
           stroke_width=stroke, stroke_fill=(255, 255, 255))


def draw_swing(hinge, other, side, tag=None, col=(40, 150, 40)):
    hx, hy = P(*hinge)
    ox, oy = P(*other)
    dx, dy = ox - hx, oy - hy
    r = math.hypot(dx, dy)
    a0 = math.degrees(math.atan2(dy, dx))
    la = math.radians(a0 + 90 * side)
    tip = (hx + r * math.cos(la), hy + r * math.sin(la))
    d.line([(hx, hy), tip], fill=col, width=4)
    pts = []
    for k in range(25):
        t = k / 24
        ang = math.radians(a0 + 90 * side * t)
        pts.append((hx + r * math.cos(ang), hy + r * math.sin(ang)))
    d.line(pts, fill=col, width=2)
    if tag:
        mxx, myy = (hx + tip[0]) / 2, (hy + tip[1]) / 2
        d.text((mxx, myy), tag, fill=(0, 100, 0), font=FT, anchor="mm",
               stroke_width=3, stroke_fill=(255, 255, 255))


def draw_slider(a, b, col_fix=(70, 150, 200), col_mov=(196, 226, 244)):
    ax, ay = P(*a)
    bx, by = P(*b)
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    n = max(2, int(round(L / PP / 1.1)))
    pw = L / n
    for i in range(n):
        cx, cy = ax + ux * pw * (i + .5), ay + uy * pw * (i + .5)
        off = 6 if i % 2 == 0 else -6
        px, py = cx + nx * off, cy + ny * off
        hw, hh = pw / 2 - 2, 7
        d.polygon([(px - ux * hw - nx * hh, py - uy * hw - ny * hh),
                   (px + ux * hw + nx * hh, py + uy * hw + ny * hh),
                   (px + ux * hw - nx * hh, py + uy * hw - ny * hh),
                   (px - ux * hw + nx * hh, py - uy * hw + ny * hh)],
                  fill=col_fix if i % 2 == 0 else col_mov, outline=(60, 140, 180))


# ── 房间 ─────────────────────────────────────────────────────
for r in g["rooms"]:
    outline(r["polygon_m"], (215, 65, 65))
    xs = [p[0] for p in r["polygon_m"]]
    ys = [p[1] for p in r["polygon_m"]]
    label((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
          f'{r["id"]} {r["name"]}', (150, 0, 0), F)

# ── 飘窗：房间的抬高台面 ──────────────────────────────────────
for r in g["rooms"]:
    for b in r.get("bays", []):
        outline(b, (120, 120, 120), 2, dash=True)
        xs = [p[0] for p in b]
        ys = [p[1] for p in b]
        label((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
              f'飘窗（{r["name"]} 的抬高台面 · 台高 0.5m）', (90, 90, 90), FT)

# ── 旧编号对照框 ─────────────────────────────────────────────
# v5 那版数据里两个飘窗各有独立 id（R9 主卧飘窗 / R10 小孩房飘窗）。
# 用户上次就是对着 v5 图问「R10 是啥」——这里在新图上把它圈出来，
# 避免再出现「提问不说清是哪张图哪个编号」的沟通成本。
for (x0, y0, x1, y1), note in OLD_ID_NOTE:
    d.rectangle([P(x0, y0), P(x1, y1)], outline=(230, 30, 30), width=4)
    label((x0 + x1) / 2, y1 + 0.28, note, (200, 0, 0), FT)

# ── 门 ───────────────────────────────────────────────────────
for dr in g["doors"]:
    if dr["type"] == "swing":
        draw_swing(dr["hinge_m"], dr["opening_m"][1], dr.get("side", 1), dr["id"])
    else:
        draw_slider(tuple(dr["opening_m"][0]), tuple(dr["opening_m"][1]))
        mid = P((dr["opening_m"][0][0] + dr["opening_m"][1][0]) / 2,
                (dr["opening_m"][0][1] + dr["opening_m"][1][1]) / 2)
        d.text((mid[0] + 8, mid[1]), f'{dr["id"]} 玻璃移门', fill=(0, 100, 150),
               font=FT, anchor="lm", stroke_width=3, stroke_fill=(255, 255, 255))

# ── 窗 ───────────────────────────────────────────────────────
for w in g.get("windows", []):
    o = w["opening_m"]
    d.line([P(*o[0]), P(*o[1])], fill=(190, 0, 190), width=5)

# ── 公卫三进标注 ─────────────────────────────────────────────
for (lx, ly), txt, col in GW_NOTES:
    label(lx, ly, txt, col, FT)
label(GW_FLOW[0][0], GW_FLOW[0][1], GW_FLOW[1], (0, 110, 40), FT, 3, "lm")

# ── 裁剪 + 图例 ──────────────────────────────────────────────
img = img.crop((max(0, int(X0 * PP)), max(0, int(Y0 * PP)),
                min(img.width, int(X1 * PP)), min(img.height, int(Y1 * PP))))

BANNER = [
    ("理解平面图 v6 ｜ 画的是 pipeline 实际产出的数据（room-graph.json），不再手工重画", (0, 0, 0)),
    ("红=房间(标注数据编号 R0/R1…)  橙=墙  绿=平开门(弧线方向=开向，读自图上门扇符号)", (0, 0, 0)),
    ("蓝=玻璃移门  紫=窗  灰虚线=飘窗(已并入所属房间，是 0.5m 抬高台面，不是独立房间)", (0, 0, 0)),
    ("本轮修正：① 公卫去除假墙，成一整间(淋浴→马桶→门外盥洗龛) ② 飘窗并入主卧/衣帽间 ③ 门开向改由门扇判读", (170, 0, 0)),
    ("红粗框 = 上一版(v5)数据的旧编号位置，方便与上次的提问逐条对上", (200, 0, 0)),
]


def wrap(txt, fnt, maxw):
    lines, cur = [], ""
    for ch in txt:
        if d.textlength(cur + ch, font=fnt) <= maxw or not cur:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


rows = []
for txt, col in BANNER:
    for ln in wrap(txt, FS, img.width - 14):
        rows.append((ln, col))
BH = 8 + 23 * len(rows) + 6
bar = Image.new("RGB", (img.width, BH), "white")
bd = ImageDraw.Draw(bar)
for i, (ln, col) in enumerate(rows):
    bd.text((8, 6 + 23 * i), ln, fill=col, font=FS)
out = Image.new("RGB", (img.width, img.height + BH), "white")
out.paste(bar, (0, 0))
out.paste(img, (0, BH))
fn = f"{ROOT}/data/v6/plan_v6_{mode}.png"
out.save(fn)
print("SAVED", fn, out.size)
