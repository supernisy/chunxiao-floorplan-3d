"""geom_v6.py — 严格正交的墙 / 房间 / 门窗重建（v5 三个根因的修复版）。

v5 暴露的三个问题与 v6 的对策
────────────────────────────────────────────────────────────────
P1 「斜墙 / 黑三角」
   根因：COLUWL-HATCH 的斜向填充线被整层当墙。→ 沿用 v5 的**轴向过滤**（已解决）。

P2 公卫（厨房旁卫生间）被切出黑楔、只剩 1.5 m²
   根因：门扇符号（P-DOOR）画在**开启位置**，门扇本体是伸进房间的细长矩形；
        把它当墙加进 barrier，就在房间里划出一条"假墙"。
   → v6：barrier **不含 P-DOOR 原始图元**；洞口改用**门实例反推的洞口线段**封堵。

P3 旧房间集当 scope 会继承旧管线的垃圾多边形
   → v6：内外判定改用「结构外皮形态学闭合 → 填外轮廓」求**户型包络**，
         不再依赖旧房间多边形；旧多边形只用来给连通域**贴名字**。

门/窗类型（按图例，从矢量聚类，不靠像素比例猜）
     P-DOOR  #FF7F00 橙（含 curve 开启弧）+ 近正方形 bbox  → swing  平开门
     P-DOOR  2~4 个平行错开细长矩形、无弧（bbox 长宽比 ≥ 3）→ sliding 推拉/玻璃移门
     COMM-GLAZ-SECT #DDA56E 棕色剖线                        → window 窗

关键实现：**洞口线段反推**
     平开门实例 bbox 是 L×L 正方形，墙必落在 bbox 的某条边上。
     用探针在 bbox 四侧外沿扫描墙掩膜密度，最大者即墙向与墙线位置；
     洞口线段 = 沿墙线、跨度 = bbox 在该方向的跨度。
     推拉门实例 bbox 是细长条，长轴即墙向。

输出（app/src/data/）：walls_poly.json / room-graph.json / roof_poly.json
中间图（data/v6/）便于人眼复核。
"""
import os, sys, json, math
import numpy as np, cv2
from collections import Counter, defaultdict
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom_v5 as G5

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
APPDATA = os.path.join(ROOT, "app", "src", "data")
V6 = os.path.join(DATA, "v6")
PT_PER_M, PP = G5.PT_PER_M, G5.PP
W, H = G5.W, G5.H
LAYERS = G5.LAYERS

CLOSE_M = 0.26
SKIN_CLOSE_M = 0.90
MIN_ROOM_M2 = 0.45
STRIP_HALF_M = 0.07          # 洞口封堵薄条半宽

DOOR_L, GLASS_L = "P-DOOR", "A-通-门窗剖线.....COMM-GLAZ-SECT"
RAIL_L = "A-平-栏杆扶手.....FLOR-RAIL"
EXCLUDE_NAMES = {"电梯厅", "楼梯间", "消防电梯", "普通电梯", "前室", "管井",
                 "未命名", "候梯厅"}


# ══════════════════════════════════════════════════════════════════
# 人工裁定表 —— 图纸判读有歧义处的真值注入。每条都注明 PDF 依据，
# 便于日后复核；不依赖「调参碰运气」。
# ══════════════════════════════════════════════════════════════════
# (1) 公卫（厨房旁）周边：删掉「补窄缝」产生的假封堵。
#     依据：① 管井西墙 (x≈11.42) 只到 y2.62，其下陷入空旷，竖直扫描把
#           它当成 0.9m 窄缝；② 淋浴玻璃剖线的端头被当成水平窄缝。
#           两条封堵叠加后把公卫**纵切**，实测只剩 1.73 m²（应为 2.50 m²）。
#           公卫的洞口由门实例（seal_instances）给出，该处不需要补窄缝。
# (2) 飘窗带：飘窗与其房间之间只有窗台边线（P-WALL FIN #00FFFF +
#     P-WALL #545454 轻质线），**不是分隔墙**。
#     依据：用户裁定「飘窗就是所属房间的一块 0.5m 抬高台面，不是独立空间」。
#     该带上的窄缝封堵会把飘窗切成独立小房间，必须清除。
SEAL_SUPPRESS_ROI = [
    (10.28, 1.55, 11.96, 4.62),      # 公卫湿区 + 门外盥洗龛
    (7.15, 16.06, 10.95, 16.34),     # 主卧 ↔ 主卧飘窗
    (11.86, 16.06, 14.55, 16.34),    # 瑶瑶衣帽间 ↔ 其飘窗
]
# (3) 管井（公卫东北角，x11.42-11.90 / y1.63-2.62）不是户内可用空间，整块丢弃。
SHAFT_ROI = [(11.38, 1.58, 11.96, 2.68)]
# (2b) 飘窗带上「门实例」封堵同样要抑制：那里的 P-DOOR 图元是飘窗栏杆，
#     被误当成门实例后横在飘窗与房间之间，会把飘窗挡成独立房间。
#     注意公卫 ROI 不在本表内 —— 公卫的门实例（D14）是**真门**，必须保留。
SEAL_SUPPRESS_DOP_ROI = [
    (7.15, 16.06, 10.95, 16.34),     # 主卧 ↔ 主卧飘窗
    (11.86, 16.06, 14.55, 16.34),    # 瑶瑶衣帽间 ↔ 其飘窗
]
# (4) 飘窗并入其所属房间（用户裁定）。键=飘窗旧名，值=所属房间旧名。
BAY_MERGE = {"主卧飘窗": "主卧套间", "小孩房飘窗": "瑶瑶衣帽间"}
# (5) 门开向兜底：门扇符号（P-DOOR 橙）质心缺失时，按此表给 side。
#     side=+1 → 门扇朝洞口法线 (-uy, ux) 一侧开（与 App.jsx 的渲染约定一致）。
DOOR_SIDE_FIX = {}



# ══════════════════════════════════════════════════════════════════
def raster_layer(layer, colors=None, thickness=3, axis_only=True):
    img = np.zeros((H, W), np.uint8)
    n = 0
    for it in LAYERS.get(layer, []):
        c = (it.get("color") or "").upper()
        if colors and not any(c.startswith(x) for x in colors):
            continue
        pts = it.get("pts") or []
        if len(pts) < 2:
            continue
        if it.get("kind") == "poly":
            cv2.fillPoly(img, [np.array([G5.to_px(p) for p in pts], np.int32)], 255)
        else:
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                if axis_only and not G5._axis_ok(a, b):
                    continue                 # 轴向过滤：正交性的根本保证
                cv2.line(img, G5.to_px(a), G5.to_px(b), 255, thickness, cv2.LINE_8)
        n += 1
    return img, n


def _in_rois(pt, rois):
    x, y = pt
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in rois)


def _seg_mid(o):
    """洞口线段中点（op 用 a0/a1/line，gap 用 opening_m）。"""
    if "a0" in o:
        return ((o["a0"] + o["a1"]) / 2, o["line"]) if o["ori"] == "h" \
            else (o["line"], (o["a0"] + o["a1"]) / 2)
    p0, p1 = o["opening_m"]
    return ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)


def _comp_center_in_rois(stats, i, rois):
    x, y, w, h, _ = stats[i]
    return _in_rois(((x + w / 2) / PP, (y + h / 2) / PP), rois)


def build_wall():
    """结构墙掩膜。

    **不含 P-WALL FIN**（墙面面层）：它是沿房间内周画的装饰线，会横跨门洞、
    沿洗手台/窗台走线，一旦当墙就会在房间内部制造假墙（公卫被它从中间切开、
    飘窗被切成两三块）。
    """
    spec = [("P-WALL", ["#0000FF", "#FF00FF"], True),
            ("A-通-墙...........COMM-WALL", None, True),
            ("S-柱墙-模板线.....COLUWL-LINE1", None, True),
            ("S-柱墙-填充.......COLUWL-HATCH", None, True)]
    img = np.zeros((H, W), np.uint8)
    cnt = {}
    for name, cols, ax in spec:
        m, n = raster_layer(name, cols, axis_only=ax)
        cnt[name] = n
        img = cv2.bitwise_or(img, m)
    k = int(round(CLOSE_M * PP)) | 1
    solid = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    solid, kept, tot = G5.drop_small(solid, 0.04)
    print(f"  墙: 闭合 k={k}px({CLOSE_M}m) 连通域 {tot}->{kept} "
          f"面积 {int((solid>0).sum())/PP/PP:.2f} m2")
    return solid


def build_skin(wall):
    """结构外皮 = 结构墙 ∪ 面层线 ∪ 玻璃剖线 ∪ 栏杆。

    FIN（面层）在这里是必须的：图纸外墙上有一部分线只画在 FIN 层，
    少了它包络就会有洞、外轮廓填不满（实测包络会从 175 m² 缩到 116 m²，
    LDK 整间被排除在包络外）。但 FIN 不能进 barrier（见 build_wall）。
    """
    fin, _ = raster_layer("P-WALL FIN", ["#00FFFF"])
    # ⚠️ 踩坑记录（「房间出现斜角」的最后一块拼图）：
    #   玻璃剖线 / 栏杆这两层里含**斜向图元**（异形设备平台、斜栏杆）。
    #   早先它们按 axis_only=False 进外皮，斜线一路传下去：
    #   skin → skin_closed → envelope → free=(barrier==0)&(env>0) → 房间轮廓，
    #   公卫西北角就是这样被切出一个 0.14×0.25 m 的斜角（末端表现为 60 级
    #   0.01 m 锯齿斜线）。这两层对「闭合外轮廓」不是必需的（窗/阳台的闭合
    #   本就靠结构墙 + FIN 完成），因此统一做轴向过滤，从源头根除斜线。
    g, _ = raster_layer(GLASS_L, axis_only=True)
    r, _ = raster_layer(RAIL_L, axis_only=True)
    return cv2.bitwise_or(cv2.bitwise_or(cv2.bitwise_or(wall, fin), g), r)


def _axis_close(m, k):
    """轴向（1D 核）形态学闭合 = 水平闭合 ∪ 垂直闭合。

    ⚠️ 踩坑记录（「房间出现斜墙」的根因之一）：
       用方形核 np.ones((k,k)) 做闭合时，形状的**凹角**会被沿对角线磨成 45° 阶梯 ——
       k=0.9m 时阶梯长达 0.9m；随后 findContours 的 CHAIN_APPROX_SIMPLE 又把它
       压成一条 0.9m 的 45° 斜边；房间掩膜 (barrier==0)&(env>0) 就此继承斜边。
       改用 1D 核：膨胀/腐蚀只沿单一轴进行，产物边界恒为轴向，不再产生斜线。
       代价是封不住「严格对角」的缺口，故连做两轮并叠加横竖两向（见下）。"""
    h = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((1, k), np.uint8))
    v = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, 1), np.uint8))
    return cv2.bitwise_or(h, v)


def build_envelope(skin, close_m=SKIN_CLOSE_M, min_area=20.0):
    k = int(round(close_m * PP)) | 1
    s = _axis_close(skin, k)
    s = _axis_close(s, k)
    # NONE：SIMPLE 会把轴向阶梯压成 45° 斜边（同上）
    cnts, _ = cv2.findContours(s, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    env = np.zeros((H, W), np.uint8)
    kept = 0
    for c in cnts:
        if cv2.contourArea(c) < min_area * PP * PP:
            continue
        cv2.drawContours(env, [c], -1, 255, -1)
        kept += 1
    print(f"  包络: 外皮闭合 k={k}px({close_m}m) 外轮廓 {len(cnts)}->{kept} "
          f"面积 {int((env>0).sum())/PP/PP:.1f} m2")
    return env, s


# ══════════════════════════════════════════════════════════════════
def door_instances():
    gray, _ = raster_layer(DOOR_L, ["#808080"], axis_only=False)
    orange, _ = raster_layer(DOOR_L, ["#FF7F00"], axis_only=False)
    allm = cv2.bitwise_or(gray, orange)
    m = cv2.morphologyEx(allm, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 80:
            continue
        bw, bh = w / PP, h / PP
        aspect = max(bw, bh) / max(1e-6, min(bw, bh))
        # 门扇符号（橙色 P-DOOR）的质心 —— 判定开向用：
        # 门扇画在「实际开启位置」，其质心必落在洞口线**开门那一侧**。
        sub = (lab[y:y + h, x:x + w] == i)
        oy_, ox_ = np.nonzero((orange[y:y + h, x:x + w] > 0) & sub)
        if len(ox_):
            oxc, oyc = float(ox_.mean()), float(oy_.mean())
            orange_c = [round((x + oxc) / PP, 3), round((y + oyc) / PP, 3)]
            orange_r = round(float(np.hypot(ox_ - oxc, oy_ - oyc).max()) / PP, 3)
        else:
            orange_c = [round(cent[i][0] / PP, 3), round(cent[i][1] / PP, 3)]
            orange_r = 0.0
        out.append({"bbox": [x / PP, y / PP, (x + w) / PP, (y + h) / PP],
                    "cx": cent[i][0] / PP, "cy": cent[i][1] / PP,
                    "bw": round(bw, 3), "bh": round(bh, 3), "aspect": round(aspect, 2),
                    "kind": "sliding" if aspect >= 3.0 else "swing",
                    "orange_c": orange_c, "orange_r": orange_r,
                    "orange_px": int((orange[y:y + h, x:x + w] > 0).sum())})
    return out


def glass_instances():
    g, _ = raster_layer(GLASS_L, axis_only=False)
    m = cv2.morphologyEx(g, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 300:
            continue
        out.append({"bbox": [x / PP, y / PP, (x + w) / PP, (y + h) / PP],
                    "cx": cent[i][0] / PP, "cy": cent[i][1] / PP,
                    "bw": round(w / PP, 3), "bh": round(h / PP, 3)})
    return out


def _band(arr, lo, hi):
    lo, hi = max(0, int(lo)), min(arr.shape[0], int(hi))
    return arr[lo:hi]


def probe_opening(inst, wall):
    """反推洞口线段：返回 (ori, 墙线坐标, 跨起, 跨止, 置信度)。

    平开门 bbox 是 L×L，墙落在 bbox 的某条边上 → 在 bbox 四侧外沿扫描墙密度。
    推拉门 bbox 是细长条，长轴即墙向。
    """
    x0, y0, x1, y1 = inst["bbox"]

    if inst["kind"] == "sliding":
        if inst["bw"] >= inst["bh"]:                 # 水平长条 -> 墙水平
            return "h", (y0 + y1) / 2, x0, x1, 1.0
        return "v", (x0 + x1) / 2, y0, y1, 1.0

    # swing：沿 y 找墙（水平墙）与沿 x 找墙（竖直墙）比分数
    # 注意扫描范围必须**限制在 bbox 内**（±0.05m），否则探针会吸附到旁边
    # 那根贯通的长墙（公卫门曾因此被判成竖直洞口，因为西侧 0.28m 粗柱上下贯通）。
    mx = 0.05
    bx0, bx1 = (x0 - mx) * PP, (x0 - 0.01) * PP
    ax0, ax1 = (x1 + 0.01) * PP, (x1 + mx) * PP
    best_h = (-1.0, None)
    for yv in np.arange(y0 - 0.30, y1 + 0.30, 0.01):
        py = int(round(yv * PP))
        if not (0 <= py < H):
            continue
        s = 0.0
        for a, b in ((bx0, bx1), (ax0, ax1)):
            a, b = max(0, int(a)), min(W, int(b))
            if b > a:
                s += float((wall[py, a:b] > 0).mean())
        if s > best_h[0]:
            best_h = (s, yv)

    mx = 0.05
    by0, by1 = (y0 - mx) * PP, (y0 - 0.01) * PP
    ay0, ay1 = (y1 + 0.01) * PP, (y1 + mx) * PP
    best_v = (-1.0, None)
    for xv in np.arange(x0 - 0.30, x1 + 0.30, 0.01):
        px = int(round(xv * PP))
        if not (0 <= px < W):
            continue
        # 墙线必须落在 bbox 自身跨度内（略有 0.05m 余量）
        if not (x0 - 0.05 <= xv <= x1 + 0.05):
            continue
        s = 0.0
        for a, b in ((by0, by1), (ay0, ay1)):
            a, b = max(0, int(a)), min(H, int(b))
            if b > a:
                s += float((wall[a:b, px] > 0).mean())
        if s > best_v[0]:
            best_v = (s, xv)
    if best_v[0] > best_h[0]:
        return "v", best_v[1], y0, y1, best_v[0]
    return "h", best_h[1], x0, x1, best_h[0]


def detect_gaps2(wall, min_w=0.25, narrow_max=1.2, wide_max=2.8, win=0.9, cover_min=0.50):
    """分级洞口检测（比 v5 的单一判据更贴合本图）。

      · 窄口 (min_w, narrow_max]  —— 门/窄缝，直接收（不需要覆盖率佐证）
      · 宽口 (narrow_max, wide_max] —— 需要局部墙体覆盖率 ≥ cover_min
                                     （挡掉"扫描线穿整间房"造成的假洞口）

    v5 的单判据（gap ∈ [0.55,2.8] 且 cover ≥ 0.5）会把公卫门洞拒掉：
    该处一侧是 0.2m 粗柱，窗口内墙占比只有 0.41。
    """
    cands = []
    mn, nmx, wmx = int(min_w * PP), int(narrow_max * PP), int(wide_max * PP)
    Wn = int(win * PP)

    def scan(line, coord, ori):
        segs = G5._runs(line)
        for a, b in zip(segs, segs[1:]):
            g0, g1 = a[1], b[0]
            L = g1 - g0
            if not (mn <= L <= wmx):
                continue
            if L > nmx:
                lo, hi = max(0, g0 - Wn), min(len(line), g1 + Wn)
                if (line[lo:hi] > 0).mean() < cover_min:
                    continue
            cands.append([ori, coord, g0, g1])

    for r in range(0, H, 2):
        scan(wall[r] > 0, r, "h")
    for c in range(0, W, 2):
        scan(wall[:, c] > 0, c, "v")

    groups = []
    for ori, p, a0, a1 in sorted(cands, key=lambda t: (t[0], t[1], t[2])):
        for g in groups:
            if g["ori"] != ori or abs(g["p_last"] - p) > 6:
                continue
            ov = min(g["a1"], a1) - max(g["a0"], a0)
            if ov < 0.7 * min(g["a1"] - g["a0"], a1 - a0):
                continue
            g["ps"].append(p)
            g["a0"], g["a1"] = max(g["a0"], a0), min(g["a1"], a1)
            g["p_last"] = p
            break
        else:
            groups.append({"ori": ori, "ps": [p], "a0": a0, "a1": a1, "p_last": p})

    out = []
    for g in groups:
        if g["a1"] - g["a0"] < min_w * PP:
            continue
        p = float(np.median(g["ps"])) / PP
        a0, a1 = g["a0"] / PP, g["a1"] / PP
        seg = ([[round(a0, 3), round(p, 3)], [round(a1, 3), round(p, 3)]] if g["ori"] == "h"
               else [[round(p, 3), round(a0, 3)], [round(p, 3), round(a1, 3)]])
        out.append({"ori": g["ori"], "opening_m": seg, "width_m": round(a1 - a0, 3)})
    return out


def old_name_raster(old):
    """旧房间名 -> 像素索引图，用于「封堵合法性仲裁」。"""
    idx = np.zeros((H, W), np.int16)
    for n, r in enumerate(old, 1):
        m = np.zeros((H, W), np.uint8)
        pts = np.array([[int(round(p[0] * PP)), int(round(p[1] * PP))]
                        for p in r["polygon_m"]], np.int32)
        cv2.fillPoly(m, [pts], 255)
        idx[(m > 0) & (idx == 0)] = n
    return idx, [r["name"] for r in old]


def seal_ok(ori, line, a0, a1, oidx, onames, probe=0.40):
    """封堵合法性仲裁。

    一条封堵条如果**两侧同属一个旧房间**，说明它落在房间内部（是图纸上的
    洗手台沿线、飘窗中缝、面层线等噪声造成的假洞口），必须丢弃——
    否则房间会被从中间切成两三块（主卧套间曾被切成 13.7+1.9+1.8）。
    """
    mid = (a0 + a1) / 2
    if ori == "h":
        pa, pb = (mid, line - probe), (mid, line + probe)
    else:
        pa, pb = (line - probe, mid), (line + probe, mid)

    def nm(p):
        px, py = int(p[0] * PP), int(p[1] * PP)
        if not (0 <= px < W and 0 <= py < H):
            return None
        v = int(oidx[py, px])
        return onames[v - 1] if v > 0 else None

    na, nb = nm(pa), nm(pb)
    if na and nb and na == nb:
        return False
    return True


def opening_instances(dinst, ginst, wall):
    """所有开洞（门 + 窗/玻璃）统一成洞口线段。"""
    ops = []
    for d in dinst:
        ori, c, a0, a1, sc = probe_opening(d, wall)
        ops.append({"ori": ori, "line": c, "a0": round(a0, 3), "a1": round(a1, 3),
                    "width_m": round(a1 - a0, 3), "type": d["kind"], "score": round(sc, 2),
                    "src": "door", "orange_c": d.get("orange_c")})
    for g in ginst:
        if g["bw"] >= g["bh"]:
            ops.append({"ori": "h", "line": (g["bbox"][1] + g["bbox"][3]) / 2,
                        "a0": g["bbox"][0], "a1": g["bbox"][2],
                        "width_m": round(g["bw"], 3), "type": "window", "score": 1.0,
                        "src": "glass"})
        else:
            ops.append({"ori": "v", "line": (g["bbox"][0] + g["bbox"][2]) / 2,
                        "a0": g["bbox"][1], "a1": g["bbox"][3],
                        "width_m": round(g["bh"], 3), "type": "window", "score": 1.0,
                        "src": "glass"})
    return ops


def seal_instances(ops, half_m=STRIP_HALF_M, over_m=0.18):
    """把洞口线段封成薄条。

    **两端各外延 over_m**：洞口线段的端点往往比实际墙洞短 3~8cm（门框/门槛石
    的绘图边界），不外延就会留下细缝——客厅阳台的推拉门两端各留 5cm 缝，
    结果整个阳台 7.5 m² 从缝里漏进 LDK。
    """
    s = np.zeros((H, W), np.uint8)
    hf = int(round(half_m * PP))
    for o in ops:
        if o["a1"] - o["a0"] < 0.25:
            continue
        c = o["line"]
        a0, a1 = o["a0"] - over_m, o["a1"] + over_m
        if o["ori"] == "h":
            py = int(round(c * PP))
            if 0 <= py < H:
                cv2.rectangle(s, (int(a0 * PP), py - hf), (int(a1 * PP), py + hf), 255, -1)
        else:
            px = int(round(c * PP))
            if 0 <= px < W:
                cv2.rectangle(s, (px - hf, int(a0 * PP)), (px + hf, int(a1 * PP)), 255, -1)
    return s


# ══════════════════════════════════════════════════════════════════
def old_rooms():
    return json.load(open(os.path.join(DATA, "room-graph.json"), encoding="utf-8"))["rooms"]


def seed_raster(old, erode_m=0.10):
    seedid = np.zeros((H, W), np.int32)
    id2name, k = {}, 0
    ek = int(round(erode_m * PP)) | 1
    for r in old:
        m = np.zeros((H, W), np.uint8)
        pts = np.array([[int(round(p[0] * PP)), int(round(p[1] * PP))]
                        for p in r["polygon_m"]], np.int32)
        cv2.fillPoly(m, [pts], 255)
        m = cv2.erode(m, np.ones((ek, ek), np.uint8))
        if not m.any():
            continue
        k += 1
        seedid[m > 0] = k
        id2name[k] = r["name"]
    return seedid, id2name


def nearest_seed(seedid):
    src = (seedid == 0).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 3,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    mx = int(labels.max())
    mp = np.zeros(mx + 1, np.int32)
    blk = labels[seedid > 0].ravel()
    sid = seedid[seedid > 0].ravel()
    o = np.argsort(blk, kind="stable")
    blk, sid = blk[o], sid[o]
    first = np.ones(len(blk), bool)
    if len(blk) > 1:
        first[1:] = blk[1:] != blk[:-1]
    mp[blk[first]] = sid[first]
    return mp[labels]


def main():
    os.makedirs(V6, exist_ok=True)
    print("[1] 墙掩膜（轴向过滤）")
    wall = build_wall()
    cv2.imwrite(os.path.join(V6, "wall.png"), wall)

    print("[2] 户型包络（结构外皮闭合 + 填外轮廓）")
    skin = build_skin(wall)
    env, skin_c = build_envelope(skin)
    cv2.imwrite(os.path.join(V6, "skin_closed.png"), skin_c)
    cv2.imwrite(os.path.join(V6, "envelope.png"), env)

    print("[3] 门/窗实例 → 洞口线段")
    old = old_rooms()
    oidx, onames = old_name_raster(old)
    dinst = door_instances()
    ginst = glass_instances()
    # 只有"门"用来封堵（分隔房间）。玻璃剖线是窗/飘窗栏杆的细线构件，
    # 一旦进 barrier 就会把飘窗、阳台沿中缝切成两半 -> 只作窗户元数据。
    ops = opening_instances(dinst, ginst, wall)
    ops = [o for o in ops if o["width_m"] >= 0.25]
    dop = [o for o in ops if o["src"] == "door"]
    n0 = len(dop)
    dop = [o for o in dop if seal_ok(o["ori"], o["line"], o["a0"], o["a1"], oidx, onames)]
    n_d1 = len(dop)
    dop = [o for o in dop if not _in_rois(_seg_mid(o), SEAL_SUPPRESS_DOP_ROI)]
    if n_d1 != len(dop):
        print(f"  人工裁定：抑制飘窗带栏杆实例 {n_d1} -> {len(dop)}")
    print(f"  门实例 {len(dinst)} / 玻璃实例 {len(ginst)} -> 开洞 {len(ops)}"
          f"（门 {n0} -> 仲裁后 {len(dop)}）")
    seal_d = seal_instances(dop)
    gaps = detect_gaps2(wall)
    gaps = [g for g in gaps if g["width_m"] <= 1.35]      # 只补窄缝，宽口交给门实例
    m0 = len(gaps)
    gaps = [g for g in gaps if not _in_rois(_seg_mid(g), SEAL_SUPPRESS_ROI)]
    if m0 != len(gaps):
        print(f"  人工裁定：抑制公卫/飘窗带假窄缝 {m0} -> {len(gaps)}")
    gaps = [g for g in gaps
            if seal_ok(g["ori"], g["opening_m"][0][1] if g["ori"] == "h" else g["opening_m"][0][0],
                       min(g["opening_m"][0][0], g["opening_m"][1][0]) if g["ori"] == "h"
                       else min(g["opening_m"][0][1], g["opening_m"][1][1]),
                       max(g["opening_m"][0][0], g["opening_m"][1][0]) if g["ori"] == "h"
                       else max(g["opening_m"][0][1], g["opening_m"][1][1]),
                       oidx, onames)]
    print(f"  补窄缝 {m0} -> 仲裁后 {len(gaps)}")
    seal_g = G5.seal_gaps(gaps, wall)
    seal = cv2.bitwise_or(seal_d, seal_g)
    cv2.imwrite(os.path.join(V6, "seal_inst.png"), seal_d)
    cv2.imwrite(os.path.join(V6, "seal_gaps.png"), seal_g)

    print("[4] 房间分割")
    barrier = cv2.bitwise_or(wall, seal)
    kc = int(round(0.14 * PP)) | 1        # 再闭一次，吃掉 <0.14m 的端部细缝
    barrier = cv2.morphologyEx(barrier, cv2.MORPH_CLOSE, np.ones((kc, kc), np.uint8))
    free = ((barrier == 0) & (env > 0)).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(free, 4)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_ROOM_M2 * PP * PP]
    n_k0 = len(keep)
    keep = [i for i in keep if not _comp_center_in_rois(stats, i, SHAFT_ROI)]
    if n_k0 != len(keep):
        print(f"  人工裁定：丢弃管井 {n_k0} -> {len(keep)}")
    print(f"  free 连通域 {n-1} -> 保留 {len(keep)}")

    old = old_rooms()
    seedid, id2name = seed_raster(old)
    near = nearest_seed(seedid)
    info = {}
    for k in keep:
        m = (lab == k)
        binc = np.bincount(near[m].ravel(), minlength=len(id2name) + 1)
        binc[0] = 0
        b = int(np.argmax(binc))
        info[k] = {"name": id2name.get(b, "未命名"),
                   "match": float(binc[b]) / max(1, int(m.sum()))}

    # 只合并**真正相邻**的同名碎片：否则同名但不连通的两块会被并成一个 label，
    # 矢量化取最大块时小块被静默丢弃（公卫就是这样丢的）。
    byname = defaultdict(list)
    for k in keep:
        byname[info[k]["name"]].append(k)
    parent = {k: k for k in keep}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for nm, ks in byname.items():
        if nm in EXCLUDE_NAMES or len(ks) < 2:
            continue
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = ks[i], ks[j]
                ma = (lab == a).astype(np.uint8)
                mb = (lab == b).astype(np.uint8)
                if (cv2.dilate(ma, np.ones((11, 11), np.uint8)) & mb).any():
                    parent[find(a)] = find(b)
    groups = defaultdict(list)
    for k in keep:
        groups[find(k)].append(k)
    merged = {}
    for ks in groups.values():
        base = max(ks, key=lambda k: stats[k, cv2.CC_STAT_AREA])
        for k in ks:
            if k != base:
                lab[lab == k] = base
            merged[k] = base
        if len(ks) > 1:
            print(f"  相邻同名碎片合并: {info[base]['name']} x{len(ks)}")
    keep = sorted(set(merged.values()))
    cv2.imwrite(os.path.join(V6, "barrier.png"), barrier)
    np.save(os.path.join(V6, "room_label.npy"), lab)

    def bb(k):
        ys, xs = np.nonzero(lab == k)
        return (f"({xs.min()/PP:.2f},{ys.min()/PP:.2f})-({xs.max()/PP:.2f},{ys.max()/PP:.2f})"
                if len(ys) else "()")

    print("  组件清单:")
    for k in sorted(keep, key=lambda k: -np.count_nonzero(lab == k)):
        print(f"    {info[k]['name']:12s} {np.count_nonzero(lab==k)/PP/PP:6.2f}m2 "
              f"match={info[k]['match']:.2f} {bb(k)}")
    kept = [k for k in keep if info[k]["name"] not in EXCLUDE_NAMES]
    dropped = [k for k in keep if info[k]["name"] in EXCLUDE_NAMES]
    print(f"  排除公摊 {len(dropped)} 间: {sorted(set(info[k]['name'] for k in dropped))}")

    vis = np.zeros((H, W, 3), np.uint8)
    rng = np.random.default_rng(7)
    for k in kept:
        vis[lab == k] = rng.integers(90, 230, 3)
    vis[wall > 0] = (255, 255, 255)
    cv2.imwrite(os.path.join(V6, "rooms_vis.png"), vis)

    print("[5] 房间矢量化")
    rooms, room_of = [], {}
    for n_, k in enumerate(sorted(kept, key=lambda k: -np.count_nonzero(lab == k))):
        m = ((lab == k).astype(np.uint8)) * 255
        polys = G5.mask_to_polys(m, ds=2, min_area=0.3)
        if not polys:
            print(f"    {info[k]['name']} 矢量化失败，跳过")
            continue
        if len(polys) > 1:                      # label 应已连通；出现多块说明有意外
            extra = sorted(polys, key=lambda g: -g.area)
            print(f"    [warn] {info[k]['name']} 有 {len(polys)} 块，"
                  f"仅取最大 {extra[0].area:.2f}，丢弃 {[round(g.area,2) for g in extra[1:]]}")
        p = max(polys, key=lambda g: g.area)
        rid = f"R{n_}"
        room_of[k] = rid
        rooms.append({"id": rid, "name": info[k]["name"], "area_m2": round(p.area, 2),
                      "polygon_m": [[round(x, 4), round(y, 4)] for x, y in p.exterior.coords],
                      "old_match": round(info[k]["match"], 2),
                      "bbox_m": [round(min(q[0] for q in p.exterior.coords), 2),
                                 round(min(q[1] for q in p.exterior.coords), 2),
                                 round(max(q[0] for q in p.exterior.coords), 2),
                                 round(max(q[1] for q in p.exterior.coords), 2)]})
    print(f"  {len(rooms)} 间: " + "、".join(f"{r['name']}{r['area_m2']}" for r in rooms))

    print("[5b] 人工裁定：飘窗并入所属房间（是房间的一块 0.5m 抬高台面，不是独立空间）")
    old_bay = defaultdict(list)
    for r in old:
        old_bay[r["name"]].append(r["polygon_m"])
    for bay_name, owner_name in BAY_MERGE.items():
        owners = [r for r in rooms if r["name"] == owner_name]
        if not owners:
            print(f"    [skip] 未找到所属房间 {owner_name}")
            continue
        own = owners[0]
        gone = [r for r in list(rooms) if r["name"] == bay_name]
        for b in gone:
            rooms.remove(b)
        if gone:
            print(f"    {bay_name} 不再作为独立房间 -> 并入 {owner_name}"
                  f"（{sum(g['area_m2'] for g in gone):.2f} m²）")
            # 兜底：若封堵没清干净，两者几何上仍隔一条窗台边线（≤0.3m），
            # 用 mitre 的 buffer±0.25 把缺口桥起来，join_style=2 保直角不引入斜边。
            op = Polygon(own["polygon_m"])
            for g in gone:
                bp = Polygon(g["polygon_m"])
                if bp.distance(op) > 0.50:
                    print(f"      [warn] 距 {owner_name} {bp.distance(op):.2f}m，仅删房间未合并几何")
                    continue
                u = unary_union([op, bp]).buffer(0.25, join_style=2).buffer(-0.25, join_style=2)
                u = max(list(u.geoms) if u.geom_type == "MultiPolygon" else [u],
                        key=lambda q: q.area)
                own["polygon_m"] = [[round(x, 4), round(y, 4)] for x, y in u.exterior.coords]
                own["area_m2"] = round(u.area, 2)
                op = u
        own.setdefault("bays", [])
        own["bays"] += old_bay.get(bay_name, [])
        print(f"    {bay_name} -> {owner_name} 的抬高台面 x{len(own['bays'])}"
              f"（台高 0.5m，与房间连通）")

    print("[6] 洞口贴房间 + 写盘")
    # 户型外洞口过滤：PDF 图里画了**邻近单元**的一部分，其门窗实例也在图层里，
    # 若不剔除就会渲染成悬在户外的门（实测 8 个：x≈3.99~8.82，全在户型左侧邻居处）。
    # 判据：洞口中点必须落在「本户型所有房间的并集」外扩 0.45m 内 ——
    # 门是装在墙上的，墙厚 0.13~0.2m，中点距房间内沿最多 ~0.1m，0.45m 足够宽松；
    # 而邻居的门距任何房间都 >1.5m，被干净排除。
    # join_style=2（mitre）保持直角：默认 buffer 会做圆角，破坏正交性
    room_union = unary_union([Polygon(r["polygon_m"]) for r in rooms]) \
        .buffer(0.45, join_style=2) if rooms else Polygon()

    def _op_mid(o):
        return ((o["a0"] + o["a1"]) / 2, o["line"]) if o["ori"] == "h" \
            else (o["line"], (o["a0"] + o["a1"]) / 2)

    n_ops = len(ops)
    ops = [o for o in ops if room_union.contains(Point(*_op_mid(o)))]
    print(f"  户型外洞口过滤 {n_ops} -> {len(ops)}（剔除邻居单元的门窗）")

    doors, windows = [], []
    for i, op in enumerate(sorted(ops, key=lambda o: -o["width_m"])):
        c = op["line"]
        mid = ((op["a0"] + op["a1"]) / 2, c) if op["ori"] == "h" else \
              (c, (op["a0"] + op["a1"]) / 2)
        ids = []
        # 沿洞口法线向两侧逐点取样（0.2~1.4m），取最先命中的房间。
        # 单点取样很容易落在封堵条/门垛上而拿不到房间。
        for sign in (-1, 1):
            for dist in np.arange(0.20, 1.45, 0.08):
                px, py = int((mid[0] + (0 if op["ori"] == "h" else sign * dist)) * PP), \
                         int((mid[1] + (sign * dist if op["ori"] == "h" else 0)) * PP)
                if not (0 <= px < W and 0 <= py < H):
                    continue
                rid = room_of.get(int(lab[py, px]))
                if rid:
                    if rid not in ids:
                        ids.append(rid)
                    break
        # 开向 side：门扇（橙）质心落在洞口法线 (-uy, ux) 一侧 → +1，否则 -1。
        # 与 App.jsx 的渲染约定一致：rotY - side*π/3。
        # 依据：P-DOOR 的门扇画在**实际开启位置**，质心必在开门那一侧。
        _oc = op.get("orange_c") or [mid[0], mid[1]]
        if op["ori"] == "h":
            side = 1 if _oc[1] > c else -1
        else:
            side = 1 if _oc[0] < c else -1
        d = {"id": f"D{i}", "type": op["type"], "ori": op["ori"],
             "edge_m": [[round(op["a0"], 3), round(c, 3)] if op["ori"] == "h"
                        else [round(c, 3), round(op["a0"], 3)],
                        [round(op["a1"], 3), round(c, 3)] if op["ori"] == "h"
                        else [round(c, 3), round(op["a1"], 3)]],
             "opening_m": [[round(op["a0"], 3), round(c, 3)] if op["ori"] == "h"
                           else [round(c, 3), round(op["a0"], 3)],
                           [round(op["a1"], 3), round(c, 3)] if op["ori"] == "h"
                           else [round(c, 3), round(op["a1"], 3)]],
             "width_m": op["width_m"], "hinge_m": [op["a0"], c] if op["ori"] == "h"
             else [c, op["a0"]], "leaf_m": op["width_m"],
             "side": side, "rooms": ids, "interior": len(ids) >= 2}
        (windows if op["type"] == "window" else doors).append(d)
    print("  类型统计:", dict(Counter(d["type"] for d in doors + windows)))
    for d in doors + windows:
        print(f"    {d['id']:4s} {d['type']:8s} w={d['width_m']:.2f} {d['ori']} "
              f"rooms={d['rooms']} @{d['opening_m'][0]}")

    wpolys = G5.mask_to_polys(wall, ds=2, min_area=0.05)
    # 墙裁剪到户型范围：PDF 图纸画了**邻近单元 + 公共走道**的墙，
    # 不裁就会在 3D 里出现大量悬空在户外的墙（实测 x≈2.8~9.5 有 4 段）。
    # 保留域 = 本户型所有房间 ∪ 外扩 0.40m（外墙厚度 ≤0.2m，0.40m 足够宽松）。
    # 用 mitre join 保证裁剪边界是直角，不会引入斜边。
    keep_zone = unary_union([Polygon(r["polygon_m"]) for r in rooms]) \
        .buffer(0.40, join_style=2) if rooms else Polygon()
    n_w = len(wpolys)
    clipped = []
    for g in wpolys:
        try:
            inter = g.intersection(keep_zone)
        except Exception:
            continue
        for p in (list(inter.geoms) if inter.geom_type == "MultiPolygon" else [inter]):
            if not p.is_empty and p.geom_type == "Polygon" and p.area >= 0.02:
                clipped.append(p)
    walls_out = [{"shell": [[round(x, 4), round(y, 4)] for x, y in g.exterior.coords],
                  "holes": [[[round(x, 4), round(y, 4)] for x, y in r.coords]
                            for r in g.interiors]} for g in clipped]
    print(f"  墙裁剪到户型 {n_w} -> {len(walls_out)} 段")
    allroom = unary_union([Polygon(r["polygon_m"]) for r in rooms]) if rooms else Polygon()
    uid = unary_union([allroom, unary_union([Polygon(w["shell"], w["holes"])
                                             for w in walls_out])])
    uid = max(list(uid.geoms) if uid.geom_type == "MultiPolygon" else [uid],
              key=lambda g: g.area)

    os.makedirs(APPDATA, exist_ok=True)
    json.dump(walls_out, open(os.path.join(APPDATA, "walls_poly.json"), "w", encoding="utf-8"))
    json.dump({"polygon_m": [[round(x, 4), round(y, 4)] for x, y in uid.exterior.coords]},
              open(os.path.join(APPDATA, "roof_poly.json"), "w", encoding="utf-8"))
    json.dump({"rooms": rooms, "doors": doors, "windows": windows,
               "checks": {"area_total_m2": round(sum(r["area_m2"] for r in rooms), 2),
                          "placed_area_m2": round(allroom.area, 2),
                          "n_rooms": len(rooms), "n_doors": len(doors),
                          "n_windows": len(windows)}},
              open(os.path.join(APPDATA, "room-graph.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"rooms": rooms, "doors": doors, "windows": windows,
               "door_instances": dinst, "glass_instances": ginst, "ops": ops},
              open(os.path.join(V6, "geom.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"  墙 {len(walls_out)} 段 / {len(rooms)} 房间 {len(doors)} 门 {len(windows)} 窗 / "
          f"套内 {round(sum(r['area_m2'] for r in rooms), 2)} m2")
    print("DONE")


if __name__ == "__main__":
    main()
