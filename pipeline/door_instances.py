"""door_instances.py — 直接从 PDF 矢量图层聚类出**门/窗实例**（不依赖像素分类猜测）。

图例语义（实测）：
  P-DOOR  #808080 灰 = 门扇/门框直线
  P-DOOR  #FF7F00 橙 = 门扇框 + **开启弧**（curve）—— 有橙弧 = 平开门 swing
  COMM-GLAZ-SECT #DDA56E 棕 = 门窗玻璃剖线（两根平行短线 + 端封）

输出：data/v5/openings.json
"""
import os, json, math
import numpy as np, cv2
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PT_PER_M = 45.36
PP = 200.0
PAGE_W_PT, PAGE_H_PT = 1191.0, 842.0
W, H = int(PAGE_W_PT / PT_PER_M * PP) + 2, int(PAGE_H_PT / PT_PER_M * PP) + 2
LAYERS = json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

DOOR = "P-DOOR"
GLASS = "A-通-门窗剖线.....COMM-GLAZ-SECT"


def to_px(p):
    return (int(round(p[0] / PT_PER_M * PP)), int(round(p[1] / PT_PER_M * PP)))


def raster_color(layer, colors):
    """只栅格化指定颜色（前缀匹配）的图元。"""
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
            cv2.fillPoly(img, [np.array([to_px(p) for p in pts], np.int32)], 255)
        else:
            for i in range(len(pts) - 1):
                cv2.line(img, to_px(pts[i]), to_px(pts[i + 1]), 255, 3, cv2.LINE_8)
        n += 1
    return img, n


def components(mask, min_px=60):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    return [(i, stats[i], cent[i]) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_px]


def inst_poly(i, lab, ds=2):
    """连通域 -> 直角多边形（米）。"""
    m = ((lab == i).astype(np.uint8)) * 255
    h, w = m.shape
    H2, W2 = h // ds, w // ds
    blk = m[:H2 * ds, :W2 * ds].reshape(H2, ds, W2, ds).mean(axis=(1, 3)) >= 0.5
    cnts, _ = cv2.findContours((blk * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 4:
        return None
    return [[round(float(p[0][0] + .5) * ds / PP, 3), round(float(p[0][1] + .5) * ds / PP, 3)] for p in c]


def main():
    gray, ng = raster_color(DOOR, ["#808080"])
    orange, no = raster_color(DOOR, ["#FF7F00"])
    glass, ngl = raster_color(GLASS, None)
    print(f"P-DOOR 灰 {ng} 条 / 橙 {no} 条 ; 玻璃剖线 {ngl} 条")

    allm = cv2.bitwise_or(gray, orange)
    comps = components(allm, min_px=80)
    print(f"门/五金实例 {len(comps)}")

    out = []
    for i, st, ce in comps:
        x, y, w, h = int(st[0]), int(st[1]), int(st[2]), int(st[3])
        sub_o = int((orange[y:y + h, x:x + w] > 0).sum())
        sub_g = int((gray[y:y + h, x:x + w] > 0).sum())
        out.append({
            "id": None, "cx": round(ce[0] / PP, 3), "cy": round(ce[1] / PP, 3),
            "bbox": [round(x / PP, 3), round(y / PP, 3), round((x + w) / PP, 3), round((y + h) / PP, 3)],
            "bw": round(w / PP, 3), "bh": round(h / PP, 3),
            "orange_px": sub_o, "gray_px": sub_g,
            "arc": sub_o > 200,          # 有开启弧 -> 平开门
        })
    out.sort(key=lambda d: (-d["bw"], d["cx"]))
    for n, d in enumerate(out):
        d["id"] = f"O{n}"
    print(f"{'id':5s} {'cx':>6s} {'cy':>6s} {'bw':>5s} {'bh':>5s} {'or':>6s} {'gray':>6s} arc")
    for d in out:
        print(f"{d['id']:5s} {d['cx']:6.2f} {d['cy']:6.2f} {d['bw']:5.2f} {d['bh']:5.2f} "
              f"{d['orange_px']:6d} {d['gray_px']:6d} {'ARC' if d['arc'] else '-'}")

    # 玻璃剖线实例（按"沿墙向"长度合并：先粗聚成大块）
    gk = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    glass_b = cv2.morphologyEx(glass, cv2.MORPH_CLOSE, gk)
    n2, lab2, st2, ce2 = cv2.connectedComponentsWithStats(glass_b, 8)
    gout = []
    for i in range(1, n2):
        if st2[i, cv2.CC_STAT_AREA] < 400:
            continue
        x, y, w, h = int(st2[i, 0]), int(st2[i, 1]), int(st2[i, 2]), int(st2[i, 3])
        gout.append({"cx": round(ce2[i][0] / PP, 3), "cy": round(ce2[i][1] / PP, 3),
                     "bbox": [round(x / PP, 3), round(y / PP, 3), round((x + w) / PP, 3), round((y + h) / PP, 3)],
                     "bw": round(w / PP, 3), "bh": round(h / PP, 3)})
    print(f"\n玻璃剖线实例 {len(gout)}（w×h，>0.5m 的段）")
    for g in sorted(gout, key=lambda g: -max(g["bw"], g["bh"]))[:30]:
        print(f"   ({g['cx']:6.2f},{g['cy']:6.2f}) {g['bw']:.2f} x {g['bh']:.2f}")

    json.dump({"doors": out, "glass": gout},
              open(os.path.join(DATA, "v5", "openings.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cv2.imwrite(os.path.join(DATA, "v5", "inst_gray.png"), gray)
    cv2.imwrite(os.path.join(DATA, "v5", "inst_orange.png"), orange)
    cv2.imwrite(os.path.join(DATA, "v5", "inst_glass.png"), glass)
    print("写 data/v5/openings.json")


if __name__ == "__main__":
    main()
