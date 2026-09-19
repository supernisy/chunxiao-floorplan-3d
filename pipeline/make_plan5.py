"""make_plan5.py — 我的理解平面图 v5（在淡化的 PDF 上画"我读出来的户型"）。

相对 v4 的改动（全部按用户裁定）：
  1. 公卫(厨房旁) = **三进**：北=淋浴间 / 中=马桶间 / 南=盥洗间(干区，向客厅开敞)。
     洗手台在**马桶正下方**（盥洗间内、贴东墙）；北段淋浴间隔断为 2 扇可动玻璃移门。
  2. 入户门：开向**外**（往走廊/电梯厅方向），门轴在东端。
  3. 飘窗：与房间**连通**、只是台高 0.5m —— 不再当独立房间，改为房间内的一块抬高台面。

用法: python pipeline/make_plan5.py [full|master|gw]
"""
import json, math, sys
import numpy as np, cv2, pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
PT_PER_M = 45.36
PDF = f"{ROOT}/assets/chunxiao.pdf"
g = json.load(open(f"{ROOT}/app/src/data/room-graph.json", encoding="utf-8"))

ROOM_LABEL = {}
SKIP_ROOMS = {"R11", "R1", "R9", "R10"}     # 公卫/主卧套间/两个飘窗 单独画

# ── 公卫（v5）：三进 + 管井 ──────────────────────────────────────
GW_SHOWER = [(10.36, 1.83), (11.24, 1.83), (11.24, 2.62), (10.36, 2.62)]
GW_TOILET_RM = [(10.36, 2.62), (11.89, 2.62), (11.89, 3.51), (10.36, 3.51)]
GW_VANITY = [(10.40, 3.67), (11.89, 3.67), (11.89, 4.52), (10.40, 4.52)]
GW_SHAFT = [(11.24, 2.16), (11.92, 2.16), (11.92, 2.66), (11.24, 2.66)]
GW_SCREEN = ((10.36, 2.62), (11.24, 2.62), 2, [])       # 淋浴隔断：2 扇可动玻璃
GW_BASIN = (11.33, 3.67, 11.89, 4.52)                    # 洗手台（贴东墙）
GW_HEAD = (11.05, 2.16)                                  # 花洒

# ── 主卧入口门（翻转）：轴在东端、向南(往主卧里)开 ────────────────
D11_FIX = {"hinge": [11.815, 12.225], "other": [10.905, 12.225], "side": -1}
# ── 入户门：轴在东端、向北(往走廊/外)开 ──────────────────────────
D9_FIX = {"hinge": [10.0, 8.575], "other": [9.05, 8.575], "side": +1}

# ── 衣帽间：一个整体空间 + 南侧一整道 3 扇玻璃移门 ───────────────
CLOSET_ZONE = [(6.90, 11.05), (11.40, 11.05), (11.40, 12.22), (6.90, 12.22)]
CLOSET_CABINET_X = (8.55, 9.44)
CLOSET_ZONE_LABELS = [("女衣帽间", 7.75, 11.72), ("男衣帽间", 10.30, 11.72)]
SLIDER_CLOSET = ((7.40, 12.22), (10.45, 12.22), 3, [1])

# ── 飘窗：与房间连通，只是台高 0.5m ─────────────────────────────
BAY = [
    ("R9", (7.24, 16.18), (10.89, 17.04), 16.18, "主卧"),
    ("R10", (11.94, 16.18), (14.49, 17.04), 16.18, "衣帽间"),
]

SLIDING_CFG = {
    "D0": (4, [1, 2]),
    "D5": (4, [1, 2]),
    "D8": (2, [0]),
}

mode = sys.argv[1] if len(sys.argv) > 1 else "full"
if mode == "master":
    X0, Y0, X1, Y1, PP = 4.2, 9.4, 13.2, 17.6, 110.0
elif mode == "gw":
    X0, Y0, X1, Y1, PP = 9.7, 1.1, 12.5, 4.9, 255.0
else:
    X0, Y0, X1, Y1, PP = 6.0, 1.0, 18.6, 17.6, 95.0

doc = pymupdf.open(PDF)
pg = doc[0]
pix = pg.get_pixmap(matrix=pymupdf.Matrix(PP / PT_PER_M, PP / PT_PER_M),
                    colorspace=pymupdf.csRGB, alpha=False)
base = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n),
                    cv2.COLOR_RGB2BGR)
base = cv2.addWeighted(base, 0.34, np.full_like(base, 255), 0.66, 0)
img = Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB)).convert("RGB")
d = ImageDraw.Draw(img)
def font(sz):
    return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", sz)
F, FS, FT = font(26), font(17), font(14)

def P(x, y):
    return (x * PP, y * PP)

# ── 从 PDF 开启弧自动推开门开向 ─────────────────────────────────
ORANGE = (1.0, 0.498, 0.0)
def _near(c, tgt, tol=0.06):
    return c and all(abs(a - b) < tol for a, b in zip(c, tgt))

def swing_sides():
    arcs = []
    for dr in pg.get_drawings():
        if "P-DOOR" not in str(dr.get("layer")) or not _near(dr.get("color"), ORANGE):
            continue
        pts = []
        for it in dr["items"]:
            if it[0] == "c":
                for s in np.linspace(0, 1, 6):
                    x = ((1 - s) ** 3 * it[1].x + 3 * (1 - s) ** 2 * s * it[2].x
                         + 3 * (1 - s) * s * s * it[3].x + s ** 3 * it[4].x) / PT_PER_M
                    y = ((1 - s) ** 3 * it[1].y + 3 * (1 - s) ** 2 * s * it[2].y
                         + 3 * (1 - s) * s * s * it[3].y + s ** 3 * it[4].y) / PT_PER_M
                    pts.append((x, y))
            elif it[0] == "l":
                pts += [(it[1].x / PT_PER_M, it[1].y / PT_PER_M),
                        (it[2].x / PT_PER_M, it[2].y / PT_PER_M)]
        if pts:
            arcs.append(pts)
    out = {}
    for dr in g["doors"]:
        if dr.get("type") != "swing" or not dr.get("hinge_m") or not dr.get("opening_m"):
            continue
        h = dr["hinge_m"]; o = dr["opening_m"]
        other = o[1] if (abs(h[0] - o[0][0]) < 1e-6 and abs(h[1] - o[0][1]) < 1e-6) else o[0]
        dx, dy = other[0] - h[0], other[1] - h[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        ssum, cnt = 0.0, 0
        for pts in arcs:
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            dm = math.hypot(cx - h[0], cy - h[1])
            if dm < 0.15 or dm > L * 1.6:
                continue
            ssum += (cx - h[0]) * nx + (cy - h[1]) * ny
            cnt += 1
        out[dr["id"]] = +1 if (cnt == 0 or ssum >= 0) else -1
    return out

SIDE = swing_sides()

# ── 基础绘制 ──────────────────────────────────────────────────
def outline(pts, color, w=3, dash=False):
    pp = [P(x, y) for x, y in pts] + [P(*pts[0])]
    if not dash:
        d.line(pp, fill=color, width=w, joint="curve")
        return
    for i in range(len(pp) - 1):
        x0, y0 = pp[i]; x1, y1 = pp[i + 1]
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

for r in g["rooms"]:
    if r["id"] in SKIP_ROOMS:
        continue
    outline(r["polygon_m"], (215, 65, 65))
    xs = [p[0] for p in r["polygon_m"]]; ys = [p[1] for p in r["polygon_m"]]
    label((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, ROOM_LABEL.get(r["id"], r["name"]))

# 主卧套间
r1 = [r for r in g["rooms"] if r["id"] == "R1"][0]
outline(r1["polygon_m"], (215, 65, 65))
label(8.4, 14.0, "主卧")
outline(CLOSET_ZONE, (150, 80, 190), 3, dash=True)
label(8.9, 11.30, "主卧衣帽间", (110, 40, 160), FS)
_c0, _c1 = CLOSET_CABINET_X
d.rectangle([P(_c0, 11.12), P(_c1, 12.05)], outline=(150, 150, 150), width=2)
label((_c0 + _c1) / 2, 11.25, "柜体", (125, 125, 125), FT, 3)
for nm, lx, ly in CLOSET_ZONE_LABELS:
    label(lx, ly, nm, (150, 95, 20), FT, 3)

# ── 飘窗：与房间连通（虚线台边 + 中文说明） ─────────────────────
for rid, (ax, ay), (bx, by), sy, owner in BAY:
    outline([(ax, ay), (bx, ay), (bx, by), (ax, by)], (120, 120, 120), 2, dash=True)
    d.line([P(ax, sy), P(bx, sy)], fill=(120, 120, 120), width=2)
    label((ax + bx) / 2, (ay + by) / 2, f"飘窗（与{owner}连通·台高0.5m）", (90, 90, 90), FT, 3)

# ── 公卫（v5）：三进 + 管井 + 洁具 ───────────────────────────────
outline(GW_SHOWER, (20, 150, 60), 3)
outline(GW_TOILET_RM, (20, 150, 60), 3)
outline(GW_VANITY, (20, 150, 60), 3)
outline(GW_SHAFT, (120, 120, 120), 2)
d.line([P(*GW_SHAFT[0]), P(*GW_SHAFT[2])], fill=(160, 160, 160), width=1)
d.line([P(GW_SHAFT[1][0], GW_SHAFT[0][1]), P(GW_SHAFT[3][0], GW_SHAFT[2][1])], fill=(160, 160, 160), width=1)
label(11.58, 2.41, "管井", (110, 110, 110), FT, 3)
label(10.78, 2.16, "淋浴间", (0, 110, 40), FT, 3)
label(10.72, 3.03, "马桶间", (0, 110, 40), FT, 3)
label(10.62, 4.30, "盥洗间(干区)", (0, 110, 40), FT, 3)
label(10.55, 4.52, "公卫=三进：淋浴→马桶→盥洗", (0, 110, 40), FT, 3, "lm")

# 花洒
_hx, _hy = GW_HEAD
for ang in range(0, 360, 45):
    r0 = 0.085
    d.line([P(_hx, _hy), P(_hx + r0 * math.cos(math.radians(ang)), _hy + r0 * math.sin(math.radians(ang)))],
           fill=(20, 150, 60), width=2)

# 洗手台：矩形台面 + 椭圆台盆 + 龙头
_bx0, _by0, _bx1, _by1 = GW_BASIN
d.rectangle([P(_bx0, _by0), P(_bx1, _by1)], outline=(20, 150, 60), width=2)
_cx, _cy = (_bx0 + _bx1) / 2, (_by0 + _by1) / 2
d.ellipse([P(_cx - 0.20, _cy - 0.26), P(_cx + 0.20, _cy + 0.26)], outline=(20, 150, 60), width=2)
d.line([P(_cx - 0.08, _cy - 0.30), P(_cx + 0.08, _cy - 0.30)], fill=(20, 150, 60), width=3)
label(11.61, 4.30, "洗手台", (0, 110, 40), FT, 3)

# 马桶：水箱(贴东墙) + 便体
d.rectangle([P(11.68, 2.90), P(11.89, 3.30)], outline=(30, 130, 130), width=2)
d.ellipse([P(11.20, 2.88), P(11.70, 3.32)], outline=(30, 130, 130), width=2)
label(11.42, 3.60, "马桶", (20, 110, 110), FT, 3)

# ── 门 ────────────────────────────────────────────────────────
def draw_swing(hinge, other, side, tag=None, col=(40, 150, 40)):
    hx, hy = P(*hinge); ox, oy = P(*other)
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
        mx, my = (hx + tip[0]) / 2, (hy + tip[1]) / 2
        d.text((mx, my), tag, fill=(0, 100, 0), font=FT, anchor="mm",
               stroke_width=3, stroke_fill=(255, 255, 255))

def draw_slider(a, b, n, fixed, col_fix=(70, 150, 200), col_mov=(190, 228, 246)):
    ax, ay = P(*a); bx, by = P(*b)
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    pw = L / n
    for i in range(n):
        cx, cy = ax + ux * pw * (i + .5), ay + uy * pw * (i + .5)
        off = 6 if i not in fixed else -6
        px, py = cx + nx * off, cy + ny * off
        hw, hh = pw / 2 - 2, 7
        quad = [(px - ux * hw - nx * hh, py - uy * hw - ny * hh),
                (px + ux * hw + nx * hh, py + uy * hw + ny * hh),
                (px + ux * hw - nx * hh, py + uy * hw - ny * hh),
                (px - ux * hw + nx * hh, py - uy * hw + ny * hh)]
        d.polygon(quad, fill=col_fix if i in fixed else col_mov, outline=(60, 140, 180))

for dr in g["doors"]:
    if dr["id"] == "D11":
        draw_swing(D11_FIX["hinge"], D11_FIX["other"], D11_FIX["side"], "主卧门")
        continue
    if dr["id"] == "D9":
        draw_swing(D9_FIX["hinge"], D9_FIX["other"], D9_FIX["side"], "入户门(外开)")
        continue
    if dr["type"] == "swing":
        o = dr["opening_m"]; h = dr["hinge_m"]
        other = o[1] if (abs(h[0] - o[0][0]) < 1e-6 and abs(h[1] - o[0][1]) < 1e-6) else o[0]
        draw_swing(h, other, SIDE.get(dr["id"], +1))
    else:
        o = dr["opening_m"]
        n, fx = SLIDING_CFG.get(dr["id"], (2, [0]))
        draw_slider(tuple(o[0]), tuple(o[1]), n, fx)
        mx, my = P((o[0][0] + o[1][0]) / 2, (o[0][1] + o[1][1]) / 2)
        d.text((mx + 8, my), f"{dr['id']} 玻璃移门", fill=(0, 100, 150), font=FT, anchor="lm",
               stroke_width=3, stroke_fill=(255, 255, 255))

# 衣帽间 3 扇移门
_ca, _cb, _cn, _cf = SLIDER_CLOSET
draw_slider(_ca, _cb, _cn, _cf)
label(6.55, 12.66, "衣帽间玻璃移门 3 扇：中间固定 / 左右可移动", (0, 100, 150), FT, 3, "lm")

# 淋浴隔断 2 扇
_ga, _gb, _gn, _gf = GW_SCREEN
draw_slider(_ga, _gb, _gn, _gf)
label(10.36, 2.50, "淋浴隔断 2 扇玻璃移门", (0, 100, 150), FT, 3, "lm")

# ── 窗 ────────────────────────────────────────────────────────
for w in g.get("windows", []):
    o = w["opening_m"]
    d.line([P(*o[0]), P(*o[1])], fill=(190, 0, 190), width=5)

# ── 裁剪 + 图例 ────────────────────────────────────────────────
img = img.crop((max(0, int(X0 * PP)), max(0, int(Y0 * PP)),
                min(img.width, int(X1 * PP)), min(img.height, int(Y1 * PP))))

BANNER = [
    ("我的理解平面图 v5 ｜ 红=房间  橙=墙  绿=平开门(弧线=开向，方向由 PDF 开启弧自动读出)", (0, 0, 0)),
    ("蓝=玻璃移门(深色=固定扇，浅色=可移动扇)  紫=窗  灰虚线=飘窗(与房间连通)  紫点线=衣帽间范围", (0, 0, 0)),
    ("本次修正：① 公卫=三进(淋浴/马桶/盥洗)，洗手台在马桶正下方、贴东墙 ② 入户门改为外开 ③ 飘窗与房间连通(台高0.5m)", (170, 0, 0)),
]

def wrap(txt, fnt, maxw):
    lines, cur = [], ""
    for ch in txt:
        if d.textlength(cur + ch, font=fnt) <= maxw or not cur:
            cur += ch
        else:
            lines.append(cur); cur = ch
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
out.paste(bar, (0, 0)); out.paste(img, (0, BH))
fn = f"{ROOT}/data/v6/plan_v5_{mode}.png"
out.save(fn)
print("SAVED", fn, out.size)
