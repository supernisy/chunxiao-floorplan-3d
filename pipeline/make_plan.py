"""基于我对 chunxiao.pdf 的理解，画一张人能读懂的户型平面图（中文标注）。
不出现任何 RGB 色值 / 图层名，只画图形 + 中文词。
输出 data/v6/my_understanding_plan.png —— 作为 3D 蓝本的审批稿。
门带编号（D0/D1...），方便你按编号指挥修改。
"""
import json, math
from PIL import Image, ImageDraw, ImageFont

ROOT = "C:/Users/super/WorkBuddy/2026-09-19-02-22-25"
g = json.load(open(f"{ROOT}/app/src/data/room-graph.json", encoding="utf-8"))
walls = json.load(open(f"{ROOT}/app/src/data/walls_poly.json", encoding="utf-8"))

S = 92                      # 米 -> 像素
ML, MT, MR, MB = 70, 95, 420, 70
xs = [p[0] for r in g["rooms"] for p in r["polygon_m"]]
ys = [p[1] for r in g["rooms"] for p in r["polygon_m"]]
xmin, xmax = min(xs), max(xs)
ymin, ymax = min(ys), max(ys)

W = int(ML + (xmax - xmin) * S + MR)
H = int(MT + (ymax - ymin) * S + MB)
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
F  = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)   # 房间名
FS = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)   # 门/窗标注/编号
FL = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)   # 图例
FID = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 12)  # 门编号

def tx(x): return ML + (x - xmin) * S
def ty(y): return MT + (ymax - y) * S      # 数据 y 向上 -> 图上靠上

# ---- 标题 ----
d.text((ML, 24), "我对这套户型的理解（请审批）", fill="#333", font=F)
d.text((W - MR + 10, 30), "灰色块=房间  黑粗线=墙", fill="#777", font=FS, anchor="rm")

# ---- 房间填充 + 名称 ----
ROOM_LABEL = {
    "R0": "客餐厅厨房(LDK)", "R1": "主卧套间", "R2": "小孩房",
    "R3": "客厅阳台", "R4": "书房", "R5": "衣帽间", "R6": "主卫",
    "R7": "小孩房阳台", "R8": "次卫", "R9": "主卧飘窗", "R10": "小孩房飘窗",
    "R11": "卫生间\n(厨房旁)",
}
for r in g["rooms"]:
    poly = [(tx(p[0]), ty(p[1])) for p in r["polygon_m"]]
    d.polygon(poly, fill="#ECECEC")
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    lab = ROOM_LABEL.get(r["id"], r["name"])
    d.text((cx, cy), lab, fill="#222", font=F, anchor="mm")

# ---- 墙 ----
for b in walls:
    shell = [(tx(p[0]), ty(p[1])) for p in b["shell"]]
    d.line(shell + [shell[0]], fill="black", width=7, joint="curve")
    for h in b.get("holes", []):
        hp = [(tx(p[0]), ty(p[1])) for p in h]
        d.line(hp + [hp[0]], fill="black", width=4)

# ---- 门 ----
def panel_rect(a, b, ux, uy, nx, ny, offset, t, fill):
    """画一扇面板（厚度 t，法向偏移 offset，填充/描边）"""
    px, py = (a[0] + b[0]) / 2 + nx * offset, (a[1] + b[1]) / 2 + ny * offset
    ux, uy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(ux, uy) or 1
    ux, uy = ux / L, uy / L
    hw, hh = L / 2 - 1, t / 2
    corners = [
        (px - ux * hw - nx * hh, py - uy * hw - ny * hh),
        (px + ux * hw + nx * hh, py + uy * hw + ny * hh),
        (px + ux * hw - nx * hh, py + uy * hw - ny * hh),
        (px - ux * hw + nx * hh, py - uy * hw + ny * hh),
    ]
    d.polygon(corners, fill=fill, outline="#5aa0b8")

def draw_arrow(a, b, ux, uy, nx, ny, offset, dir_sign, color="#5aa0b8"):
    """在面板旁画滑动方向箭头"""
    px, py = (a[0] + b[0]) / 2 + nx * offset, (a[1] + b[1]) / 2 + ny * offset
    ax, ay = px - ux * 10 * dir_sign, py - uy * 10 * dir_sign
    bx, by = px + ux * 10 * dir_sign, py + uy * 10 * dir_sign
    d.line([(ax, ay), (bx, by)], fill=color, width=2)
    # 箭头尖
    d.line([(bx, by), (bx - ux * 5 * dir_sign + nx * 3, by - uy * 5 * dir_sign + ny * 3)], fill=color, width=2)
    d.line([(bx, by), (bx - ux * 5 * dir_sign - nx * 3, by - uy * 5 * dir_sign - ny * 3)], fill=color, width=2)

def draw_swing(h_px, other_px, swing_dir="ccw", label="平开门", door_id=""):
    """画平开门：弧线表示开启方向（swing_dir='ccw' 表示逆时针扫出）"""
    hx, hy = h_px
    ox, oy = other_px
    r = math.hypot(ox - hx, oy - hy)
    ang = math.degrees(math.atan2(oy - hy, ox - hx))
    # 弧线从 leaf 方向扫 90°
    if swing_dir == "ccw":
        d.arc([hx - r, hy - r, hx + r, hy + r], int(ang), int(ang + 90), fill="#999", width=2)
    else:
        d.arc([hx - r, hy - r, hx + r, hy + r], int(ang - 90), int(ang), fill="#999", width=2)
    d.line([(hx, hy), (ox, oy)], fill="#555", width=3)
    mx, my = (hx + ox) / 2, (hy + oy) / 2
    d.text((mx, my - 10), label, fill="#1a5fb4", font=FS, anchor="mm")
    if door_id:
        d.text((mx, my + 8), door_id, fill="#444", font=FID, anchor="mm")

# 自定义门绘制覆盖：按你的纠正临时改方向/结构，仅用于平面图示意
SWING_OVERRIDE = {
    # D15: 主卫->主卧套间，改为向主卧套间（西侧）开
    "D15": "cw",
    # D11: 主卧套间入口，改为向主卧套间（北侧）开
    "D11": "ccw",
}
SLIDING_CFG = {
    # D0 客厅阳台：4 扇，中间两扇固定，左右可移动
    "D0": {"n": 4, "fixed": [1, 2], "move": [0, 3]},
    # D5 小孩房阳台：4 扇，中间两扇固定，左右可移动
    "D5": {"n": 4, "fixed": [1, 2], "move": [0, 3]},
    # D8 厨房阳台：2 扇，一扇固定，一扇移动
    "D8": {"n": 2, "fixed": [0], "move": [1]},
}

def draw_door(dr):
    h = dr["hinge_m"]; o = dr["opening_m"]
    a, b = o[0], o[1]
    ax, ay, bx, by = tx(a[0]), ty(a[1]), tx(b[0]), ty(b[1])
    hx, hy = tx(h[0]), ty(h[1])
    mx, my = (ax + bx) / 2, (ay + by) / 2
    did = dr["id"]
    if dr["type"] == "swing":
        other = b if (abs(h[0]-a[0]) < 1e-6 and abs(h[1]-a[1]) < 1e-6) else a
        ox, oy = tx(other[0]), ty(other[1])
        # 默认 ccw（与原始代码一致：从 hinge->other 逆时针 90°）
        cfg = SWING_OVERRIDE.get(did, "ccw")
        draw_swing((hx, hy), (ox, oy), swing_dir=cfg, door_id=did)
    else:  # sliding
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        cfg = SLIDING_CFG.get(did, {"n": 2, "fixed": [0], "move": [1]})
        n = cfg["n"]
        panel_w = L / n
        for i in range(n):
            px = ax + ux * panel_w * (i + 0.5)
            py = ay + uy * panel_w * (i + 0.5)
            pa = (px - ux * panel_w / 2, py - uy * panel_w / 2)
            pb = (px + ux * panel_w / 2, py + uy * panel_w / 2)
            off = 8  # 法向偏移
            if i in cfg["fixed"]:
                # 固定扇：实心
                panel_rect(pa, pb, ux, uy, nx, ny, off, 12, "#7FC4DD")
            else:
                # 移动扇：空心 + 滑动箭头
                panel_rect(pa, pb, ux, uy, nx, ny, off, 12, "#E8F4F8")
                # 箭头方向：左/右扇分别向中心滑
                dir_sign = 1 if i < (n - 1) / 2 else -1
                draw_arrow(pa, pb, ux, uy, nx, ny, off + 12, dir_sign)
        lab = "玻璃移门"
        d.text((mx, my - 10), lab, fill="#1a5fb4", font=FS, anchor="mm")
        d.text((mx, my + 8), did, fill="#444", font=FID, anchor="mm")

for dr in g["doors"]:
    draw_door(dr)

# ---- 窗 ----
for w in g.get("windows", []):
    o = w["opening_m"]; a, b = o[0], o[1]
    ax, ay, bx, by = tx(a[0]), ty(a[1]), tx(b[0]), ty(b[1])
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    for s in (-1, 1):
        d.line([(ax + nx * 3 * s, ay + ny * 3 * s), (bx + nx * 3 * s, by + ny * 3 * s)],
               fill="#2a7fb8", width=2)
    mx, my = (ax + bx) / 2, (ay + by) / 2
    d.text((mx, my - 8), "窗", fill="#2a7fb8", font=FS, anchor="mm")
    d.text((mx, my + 6), w["id"], fill="#444", font=FID, anchor="mm")

# ---- 指北 ----
d.text((ML + 14, MT - 14), "北 ↑", fill="#444", font=F, anchor="mm")

# ---- 米制刻度（顶部） ----
x = math.ceil(xmin / 2) * 2
while x <= xmax:
    px = tx(x)
    d.line([(px, MT - 6), (px, MT)], fill="#bbb", width=1)
    d.text((px, MT - 18), f"{x:.0f}m", fill="#999", font=FS, anchor="mm")
    x += 2

# ---- 图例（右侧） ----
lx = ML + (xmax - xmin) * S + 24
ly = MT + 10
d.text((lx, ly - 30), "图例", fill="#333", font=F)
items = [
    ("wall",  "墙：承重墙 / 隔墙"),
    ("swing", "平开门：弧线=开启方向"),
    ("slide", "玻璃移门：实心=固定扇，空心=移动扇"),
    ("win",   "窗"),
]
yy = ly
for kind, txt in items:
    if kind == "wall":
        d.line([(lx, yy + 10), (lx + 50, yy + 10)], fill="black", width=7)
    elif kind == "swing":
        d.arc([lx, yy, lx + 38, yy + 38], 0, 90, fill="#999", width=2)
        d.line([(lx, yy + 19), (lx + 19, yy + 19)], fill="#555", width=3)
    elif kind == "slide":
        # 示意 4 扇：中间实心，两侧空心+箭头
        panel_w = 12
        for i, fill in enumerate(["#E8F4F8", "#7FC4DD", "#7FC4DD", "#E8F4F8"]):
            x0 = lx + i * panel_w
            d.rectangle([x0, yy, x0 + panel_w - 1, yy + 18], fill=fill, outline="#5aa0b8")
        d.line([(lx + 6, yy - 4), (lx + 18, yy - 4)], fill="#5aa0b8", width=2)  # 左箭头
        d.line([(lx + 30, yy - 4), (lx + 42, yy - 4)], fill="#5aa0b8", width=2)  # 右箭头
    elif kind == "win":
        d.line([(lx, yy + 7), (lx + 50, yy + 7)], fill="#2a7fb8", width=2)
        d.line([(lx, yy + 15), (lx + 50, yy + 15)], fill="#2a7fb8", width=2)
    d.text((lx + 62, yy + 12), txt, fill="#222", font=FL, anchor="lm")
    yy += 55

# ---- 拟增加：主卫-衣帽间之间的玻璃移门（请你确认位置） ----
# 在 R6 东墙和 R5 西墙之间画一条紫色虚线示意
x_door = (11.72 + 11.94) / 2  # 两房间之间的墙
y0, y1 = 14.0, 15.8
px0, py0 = tx(x_door), ty(y0)
px1, py1 = tx(x_door), ty(y1)
# 紫色虚线 + 问号
for t in [i / 20 for i in range(21)]:
    x = px0 + (px1 - px0) * t
    y = py0 + (py1 - py0) * t
    if int(t * 10) % 2 == 0:
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill="#c44")
d.text((px0 + 12, py0 + 14), "拟增加\n玻璃移门?", fill="#c44", font=FS, anchor="lm")

img.save(f"{ROOT}/data/v6/my_understanding_plan.png")
print("SAVED", W, H)
