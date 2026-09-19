"""
visualize_overview.py — 总览叠加图：房间彩色分区 + 门符号编号 + 中文标签 + 墙线。
用于人工确认「房间语义 / 门归属 / 拓扑」。
"""
import json, os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")

meta = json.load(open(os.path.join(DATA, "masks_meta.json"), encoding="utf-8"))
scale = json.load(open(os.path.join(DATA, "scale.json"), encoding="utf-8"))
ZOOM = meta["zoom_px_per_pt"]
PX_PER_M = scale["points_per_meter"] * ZOOM

wall = cv2.imread(os.path.join(DATA, "mask_wall.png"), 0)
combined = cv2.imread(os.path.join(DATA, "mask_closed.png"), 0)
door_sym = cv2.imread(os.path.join(DATA, "door_symbols.png"), 0)
H, W = wall.shape

# --- 房间分割（固定参数）---
CLOSE_K, DIL_K = 25, 13
b = cv2.morphologyEx(combined, cv2.MORPH_CLOSE,
                     cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_K, CLOSE_K)))
b = cv2.dilate(b, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (DIL_K, DIL_K)))
free = cv2.bitwise_not(b)
n, lab, stats, cent = cv2.connectedComponentsWithStats(free, connectivity=4)
MIN_M2 = 1.5
rooms = []
for i in range(1, n):
    area = int(stats[i, cv2.CC_STAT_AREA])
    x, y, w, h = [int(v) for v in stats[i, :4]]
    if area < MIN_M2 * PX_PER_M ** 2:
        continue
    if x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1:
        continue
    rooms.append({"cid": i, "area_m2": round(area / PX_PER_M ** 2, 2),
                  "centroid_px": (float(cent[i][0]), float(cent[i][1]))})
rooms.sort(key=lambda r: -r["area_m2"])

# --- 底图：白底黑墙线 ---
vis = np.full((H, W, 3), 255, np.uint8)
vis[wall > 0] = (60, 60, 60)
PALETTE = [(255, 190, 190), (190, 230, 190), (190, 210, 255), (255, 235, 170),
           (225, 200, 245), (185, 235, 235), (255, 215, 175), (215, 235, 175),
           (245, 195, 205), (195, 230, 245), (210, 210, 250), (240, 220, 190),
           (200, 245, 220), (250, 205, 225), (215, 245, 190), (235, 225, 205)]
for k, r in enumerate(rooms):
    m = (lab == r["cid"])
    vis[m] = PALETTE[k % len(PALETTE)]

# --- 门符号：红 ---
vis[door_sym > 0] = (0, 0, 220)

img = Image.fromarray(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
dr = ImageDraw.Draw(img)
try:
    f_lab = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
    f_sm = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    f_big = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 34)
except Exception:
    f_lab = f_sm = f_big = ImageFont.load_default()

# 房间编号
for k, r in enumerate(rooms):
    cx, cy = r["centroid_px"]
    dr.text((cx - 30, cy - 40), f"R{k}", font=f_big, fill=(160, 0, 0))
    dr.text((cx - 30, cy - 6), f"{r['area_m2']}m2", font=f_sm, fill=(0, 0, 120))

# 门符号编号
ds = json.load(open(os.path.join(DATA, "door_symbols.json"), encoding="utf-8"))
for k, d in enumerate(ds):
    cx, cy = [v * ZOOM for v in d["centroid_pt"]]
    dr.text((cx + 8, cy - 30), f"D{k}", font=f_lab, fill=(200, 0, 0))
    dr.text((cx + 8, cy - 4), f"{d['leaf_len_m']}m", font=f_sm, fill=(0, 100, 0))

# 标签文字（读已知内容：id -> 文本）
LABTXT = {
    0: "设备平台", 1: "POWDER", 2: "公卫", 3: "设备平台", 4: "洗碗机", 5: "内置小冰箱",
    6: "KITCHEN", 7: "1200沙发床", 8: "下", 9: "上", 10: "厨房", 11: "书房",
    14: "设备平台", 15: "FORMAL", 16: "DINING", 19: "餐厅", 20: "BALCONY", 21: "阳台",
    22: "FORMAL", 23: "LIVING", 24: "玄关", 25: "客厅", 26: "消防电梯", 27: "普通电梯",
    28: "普通电梯", 29: "无障碍电梯", 30: "鞋子收纳及外套挂衣区", 31: "COATROOM",
    32: "COATROOM", 33: "女衣帽间", 34: "男衣帽间", 35: "次卫", 36: "储物及棉被收纳",
    37: "小孩房", 38: "1500宽床", 39: "MASTER", 40: "BEDROOM", 41: "学习桌",
    42: "主卧", 43: "瑶瑶衣帽间", 44: "POWDER", 45: "主卫", 46: "阳台", 47: "1800宽床",
    49: "BALCONY", 50: "阳台", 51: "飘窗", 52: "飘窗抬高做梳妆台兼书桌",
}
labs = json.load(open(os.path.join(DATA, "labels.json"), encoding="utf-8"))
for l in labs:
    t = LABTXT.get(l["id"])
    if not t:
        continue
    cx, cy = [v * ZOOM for v in l["center_pt"]]
    dr.text((cx - 30, cy - 12), t, font=f_lab, fill=(0, 90, 0))

img.save(os.path.join(DATA, "overview.png"))
print("WROTE overview.png", img.size, "rooms:", len(rooms), "doors:", len(ds))
for k, r in enumerate(rooms):
    print(f"  R{k}: {r['area_m2']}m2 @ px({r['centroid_px'][0]:.0f},{r['centroid_px'][1]:.0f}) = pt({r['centroid_px'][0]/ZOOM:.0f},{r['centroid_px'][1]/ZOOM:.0f})")
