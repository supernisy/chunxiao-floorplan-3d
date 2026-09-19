"""
graph_v1.py — 拼装 room-graph.json（米制）
1) 房间标签匹配（P-TEXT 标签中心 -> 所属房间）
2) 门-房间配对：从门洞中点沿法线两侧逐点探测首个非零房间 label
3) 门禁校验：门两侧房间存在 / 无孤岛(可达性) / 面积一致性
输出 data/room-graph.json、data/graph_check.png
"""
import json, os, math
import numpy as np
import cv2
from collections import defaultdict, deque

ROOT = r"C:\Users\super\WorkBuddy\2026-09-19-02-22-25"
DATA = os.path.join(ROOT, "data")
rf = json.load(open(os.path.join(DATA, "rooms_final.json"), encoding="utf-8"))
ZOOM = rf["zoom"]
PT_PER_M = rf["pt_per_m"]
M_PER_PT = 1.0 / PT_PER_M
M_PER_PX = M_PER_PT / ZOOM
rooms = rf["rooms"]
doors = json.load(open(os.path.join(DATA, "door_symbols.json"), encoding="utf-8"))
labels = json.load(open(os.path.join(DATA, "labels.json"), encoding="utf-8"))
lab = np.load(os.path.join(DATA, "rooms_label.npy"))
lab_raw = np.load(os.path.join(DATA, "rooms_label_raw.npy"))
H, W = lab.shape

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


def room_at_pt(p):
    px, py = int(round(p[0] * ZOOM)), int(round(p[1] * ZOOM))
    if 0 <= px < W and 0 <= py < H:
        return int(lab[py, px])
    return 0


# ---- 1) 标签 -> 房间 ----
room_labels = defaultdict(list)
unmatched = []
for l in labels:
    t = LABTXT.get(l["id"])
    if not t:
        continue
    r = room_at_pt(l["center_pt"])
    if r == 0:  # 落在墙上/外，就近找
        best, bd = 0, 1e9
        for dx in range(-40, 41, 8):
            for dy in range(-40, 41, 8):
                q = (l["center_pt"][0] + dx / ZOOM, l["center_pt"][1] + dy / ZOOM)
                rr = room_at_pt(q)
                if rr and math.hypot(dx, dy) < bd:
                    best, bd = rr, math.hypot(dx, dy)
        r = best
    if r:
        room_labels[r].append(t)
    else:
        unmatched.append(t)

print("=== room labels ===")
for r in rooms:
    idx = r["idx"] + 1
    print(f"  R{r['idx']:<2} {r['area_m2']:>7}m2 labels={room_labels.get(idx, [])}")
print("  unmatched labels:", unmatched)

# ---- 2) 门 -> 两侧房间 ----
def find_room_from(mid_pt, direction, max_d=2.0, step=0.03, use_raw=True):
    for s in np.arange(0.04, max_d, step):
        p = (mid_pt[0] + direction[0] * s / M_PER_PT, mid_pt[1] + direction[1] * s / M_PER_PT)
        r = (int(lab_raw[int(round(p[1]*ZOOM)), int(round(p[0]*ZOOM))]) if 0 <= int(round(p[0]*ZOOM)) < W and 0 <= int(round(p[1]*ZOOM)) < H else 0) if use_raw else room_at_pt(p)
        if r:
            return r
    return 0


for k, d in enumerate(doors):
    Hp = d["opening_pt"][0]
    Op = d["opening_pt"][1]
    mid = ((Hp[0] + Op[0]) / 2, (Hp[1] + Op[1]) / 2)
    vx, vy = Op[0] - Hp[0], Op[1] - Hp[1]
    L = math.hypot(vx, vy) or 1e-9
    nx, ny = -vy / L, vx / L
    a = find_room_from(mid, (nx, ny))
    b = find_room_from(mid, (-nx, -ny))
    d["rooms"] = [a, b]
    d["mid_pt"] = [round(mid[0], 1), round(mid[1], 1)]

BAY = {14: "R1", 15: "R4"}                  # 飘窗 -> 附属房间（无门，依附主体）
# ---- 3) 门禁校验 ----
adj = defaultdict(set)
for d in doors:
    a, b = d["rooms"]
    if a and b and a != b:
        adj[a].add(b)
        adj[b].add(a)

all_ids = {r["idx"] + 1 for r in rooms}
reach = set()
if all_ids:
    start = next(iter(all_ids))
    q = deque([start])
    reach.add(start)
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in reach:
                reach.add(v)
                q.append(v)

checks = {
    "n_rooms": len(rooms),
    "n_doors": len(doors),
    "doors_with_two_rooms": sum(1 for d in doors if d["rooms"][0] and d["rooms"][1] and d["rooms"][0] != d["rooms"][1]),
    "doors_same_room": [k for k, d in enumerate(doors) if d["rooms"][0] == d["rooms"][1] and d["rooms"][0]],
    "doors_dangling": [k for k, d in enumerate(doors) if not (d["rooms"][0] and d["rooms"][1] and d["rooms"][0] != d["rooms"][1])],
    "rooms_reachable_from_R0": len(reach),
    "rooms_unreachable": sorted(f"R{v-1}" for v in (all_ids - reach)),
    "unreachable_are_bay_windows": sorted(all_ids - reach) == sorted(k for k in BAY),
    "area_total_m2": round(sum(r["area_m2"] for r in rooms), 2),
}
print("\n=== checks ===")
for k, v in checks.items():
    print(f"  {k}: {v}")

print("\n=== doors ===")
for k, d in enumerate(doors):
    print(f"  D{k:<2} {d['type']:>8} w={d['opening_m']:>5}m  rooms={d['rooms']}  mid={d['mid_pt']}")

# 房间命名（据标签 + 位置；公共区域另标）
NAMES = {
    1: "LDK客餐厅厨房", 2: "主卧套间", 3: "电梯厅", 4: "楼梯间", 5: "小孩房",
    6: "客厅阳台", 7: "书房", 8: "瑶瑶衣帽间", 9: "消防电梯", 10: "普通电梯",
    11: "小孩房阳台", 12: "主卫", 13: "次卫", 14: "主卧飘窗", 15: "小孩房飘窗",
    16: "公卫",
}
PUBLIC = {3, 4, 9, 10}                      # 1-based：电梯厅/楼梯间/消防电梯/普通电梯
BAY = {14: "R1", 15: "R4"}                  # 飘窗 -> 附属房间（无门，依附于主体）

graph = {
    "meta": {
        "source": "chunxiao.pdf (CAD vector, OCG layers)",
        "scale_pt_per_m": round(PT_PER_M, 3),
        "units": "meter",
        "y_axis": "down (image coords)",
        "generated_by": "pipeline/graph_v1.py",
    },
    "rooms": [
        {
            "id": f"R{r['idx']}",
            "idx": r["idx"],
            "name": NAMES.get(r["idx"] + 1, "?"),
            "is_public": (r["idx"] + 1) in PUBLIC,
            "attached_to": BAY.get(r["idx"] + 1),
            "is_bay_window": (r["idx"] + 1) in BAY,
            "area_m2": r["area_m2"],
            "center_m": r["cent_m"],
            "polygon_m": r["poly_m"],
            "labels": room_labels.get(r["idx"] + 1, []),
        } for r in rooms
    ],
    "doors": [
        {
            "id": f"D{k}",
            "type": d["type"],
            "width_m": d["opening_m"],
            "leaf_m": d["leaf_m"],
            "opening_m": [
                [round(d["opening_pt"][0][0] * M_PER_PT, 3), round(d["opening_pt"][0][1] * M_PER_PT, 3)],
                [round(d["opening_pt"][1][0] * M_PER_PT, 3), round(d["opening_pt"][1][1] * M_PER_PT, 3)],
            ],
            "hinge_m": [round(d["hinge_pt"][0] * M_PER_PT, 3), round(d["hinge_pt"][1] * M_PER_PT, 3)],
            "rooms": [f"R{r-1}" if r else None for r in d["rooms"]],
        } for k, d in enumerate(doors)
    ],
    "adjacency": {f"R{k-1}": sorted(f"R{v-1}" for v in vs) for k, vs in sorted(adj.items())},
    "checks": checks,
}
json.dump(graph, open(os.path.join(DATA, "room-graph.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# ---- 可视化 ----
vis = np.full((H, W, 3), 255, np.uint8)
PALETTE = [(255, 190, 190), (190, 230, 190), (190, 210, 255), (255, 235, 170),
           (225, 200, 245), (185, 235, 235), (255, 215, 175), (215, 235, 175),
           (245, 195, 205), (195, 230, 245), (210, 210, 250), (240, 220, 190),
           (200, 245, 220), (250, 205, 225), (215, 245, 190), (235, 225, 205)]
for r in rooms:
    vis[lab == r["idx"] + 1] = PALETTE[r["idx"] % len(PALETTE)]
for k, d in enumerate(doors):
    h = [int(v * ZOOM) for v in d["hinge_pt"]]
    o = [int(v * ZOOM) for v in d["opening_pt"][1]]
    cv2.line(vis, tuple(h), tuple(o), (0, 0, 255), 5)
    cv2.putText(vis, f"D{k}", (int((h[0] + o[0]) / 2) + 6, int((h[1] + o[1]) / 2) - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)
cv2.imwrite(os.path.join(DATA, "graph_check.png"), vis)
print("\nWROTE room-graph.json + graph_check.png")
