"""
make_masks.py — 从按图层分类的矢量图元（layers.json）合成单层 mask 位图。
不依赖彩色渲染 + HSV 阈值，图元来源确定 => mask 干净。

输出（data/）：
  mask_wall.png      纯墙（P-WALL + COMM-WALL + 柱 + 墙饰面）
  mask_door.png      纯门（P-DOOR）
  mask_glass.png     门窗剖线（COMM-GLAZ-SECT，玻璃移门/窗）
  mask_closed.png    墙 ∪ 门 ∪ 玻璃（用于房间分割：把门洞堵上）
坐标系：PDF point，y 向下。缩放 ZOOM px/pt。
本户型专用参数：ZOOM、图层名清单 —— 换素材必须改。
"""
import json, os
from collections import Counter
import numpy as np
import cv2

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
layers = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

# ---- kind 统计（确认可绘制的图元种类） ----
kc = Counter()
for lname, items in layers.items():
    for it in items:
        kc[it["kind"]] += 1
print("KIND STATS:", dict(kc))
seen = set()
for lname, items in layers.items():
    for it in items:
        k = it["kind"]
        if k not in seen:
            seen.add(k)
            print(f"SAMPLE kind={k}: {json.dumps(it, ensure_ascii=False)[:260]}")

ZOOM = 3.0
W_PT, H_PT = 1016.0, 841.0
W, H = int(W_PT * ZOOM), int(H_PT * ZOOM)

# ---- 图层分组（本户型专用） ----
# 只保留**结构墙主体**。实测以下层会污染墙带几何，已排除：
#   "S-柱墙-填充...COLUWL-HATCH"  柱 hatch 斜线（闭合后糊成块）
#   "户型刷图层$0$A-WALL-FNSH"     墙面饰面 —— 含厨房橱柜/台面轮廓线（会变成假墙）
#   "P-WALL FIN"                  墙饰面
GROUP_WALL = [
    "P-WALL",                          # 墙主体（双线）
    "A-通-墙...........COMM-WALL",      # 结构墙填充轮廓
    "S-柱墙-填充.......COLUWL-HATCH",   # 柱 hatch
    "S-柱墙-模板线.....COLUWL-LINE1",   # 柱轮廓线
    "P-WALL FIN",                      # 墙饰面 —— 含大量真墙线，**不能删**
    # ⚠️ 唯一排除项：该层实测就是**厨房橱柜/台面轮廓**（n=58，全部集中在厨房），
    #    见 data/layers_grid.png 定位证据。它会变成 3D 里的假墙+黑三角。
    #    "户型刷图层$0$A-WALL-FNSH"
]
GROUP_DOOR = ["P-DOOR"]
GROUP_GLASS = ["A-通-门窗剖线.....COMM-GLAZ-SECT"]


def to_px(p):
    return (int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM)))


def draw_items(img, items, thickness):
    for it in items:
        k, pts = it["kind"], it["pts"]
        if not pts:
            continue
        try:
            if k == "line" and len(pts) >= 2:
                cv2.line(img, to_px(pts[0]), to_px(pts[1]), 255, thickness)
            elif k == "rect" and len(pts) >= 2:
                cv2.rectangle(img, to_px(pts[0]), to_px(pts[1]), 255, thickness)
            elif k in ("poly", "quad", "curve") and len(pts) >= 2:
                arr = np.array([to_px(p) for p in pts], np.int32)
                closed = (k in ("poly", "quad"))
                cv2.polylines(img, [arr], closed, 255, thickness)
            else:
                # 兜底：按折线画
                arr = np.array([to_px(p) for p in pts], np.int32)
                cv2.polylines(img, [arr], False, 255, thickness)
        except Exception as e:
            print("draw err", k, e)
    return img


def render(names):
    img = np.zeros((H, W), np.uint8)
    th = max(2, int(round(0.72 * ZOOM)))  # 原线宽 0.72pt
    for n in names:
        if n in layers:
            draw_items(img, layers[n], th)
        else:
            print("  [warn] layer not found:", n)
    return img


wall = render(GROUP_WALL)
door = render(GROUP_DOOR)
glass = render(GROUP_GLASS)
combined = cv2.bitwise_or(cv2.bitwise_or(wall, door), glass)

for name, img in [("mask_wall", wall), ("mask_door", door),
                  ("mask_glass", glass), ("mask_closed", combined)]:
    p = os.path.join(DATA, name + ".png")
    cv2.imwrite(p, img)
    nz = int((img > 0).sum())
    print(f"WROTE {p}  size={W}x{H}  nonzero_px={nz}  ({nz/(W*H)*100:.2f}%)")

meta = {"zoom_px_per_pt": ZOOM, "img_w": W, "img_h": H,
        "groups": {"wall": GROUP_WALL, "door": GROUP_DOOR, "glass": GROUP_GLASS}}
json.dump(meta, open(os.path.join(DATA, "masks_meta.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("DONE")
