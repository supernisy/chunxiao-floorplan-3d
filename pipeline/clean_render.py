"""clean_render.py — 白底干净渲染（只看重建结果，不掺 PDF 原图）。

用法:
  python pipeline/clean_render.py full
  python pipeline/clean_render.py crop out.png mx0 my0 mx1 my1 [zoom]
"""
import os, sys, json
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
APP = os.path.join(ROOT, "app", "src", "data")
PP = 200.0

TINT = {
    "LDK客餐厅厨房": (238, 230, 227), "主卧套间": (217, 234, 224), "小孩房": (232, 224, 239),
    "书房": (242, 230, 221), "公卫": (242, 238, 223), "主卫": (242, 238, 223),
    "次卫": (242, 238, 223), "客厅阳台": (213, 233, 239), "小孩房阳台": (213, 233, 239),
    "瑶瑶衣帽间": (239, 227, 233), "主卧飘窗": (242, 229, 242), "小孩房飘窗": (242, 229, 242),
}
# 洞口配色（BGR）：swing 红 / sliding 蓝 / window 青
CLR = {"swing": (0, 0, 220), "sliding": (230, 90, 0), "window": (170, 170, 0)}


def render():
    g = json.load(open(os.path.join(APP, "room-graph.json"), encoding="utf-8"))
    walls = json.load(open(os.path.join(APP, "walls_poly.json"), encoding="utf-8"))
    H, W = 4000, 4200
    img = np.full((H, W, 3), 255, np.uint8)

    def P(p):
        return (int(round(p[0] * PP)), int(round(p[1] * PP)))

    for r in g["rooms"]:
        pts = np.array([P(p) for p in r["polygon_m"]], np.int32)
        cv2.fillPoly(img, [pts], TINT.get(r["name"], (238, 238, 238)))
    for w in walls:
        cv2.polylines(img, [np.array([P(p) for p in w["shell"]], np.int32)], True, (120, 116, 112), 4)
        for h in w.get("holes", []):
            cv2.polylines(img, [np.array([P(p) for p in h], np.int32)], True, (120, 116, 112), 4)
    for r in g["rooms"]:
        cv2.polylines(img, [np.array([P(p) for p in r["polygon_m"]], np.int32)], True, (60, 60, 60), 2)
        cx = sum(p[0] for p in r["polygon_m"]) / len(r["polygon_m"])
        cy = sum(p[1] for p in r["polygon_m"]) / len(r["polygon_m"])
        o = P((cx, cy))
        t = f"{r['name']}"
        t2 = f"{r['area_m2']} m2  [{r['id']}]"
        for i, (s, dy, sc, th) in enumerate([(t, -6, 0.9, 2), (t2, 34, 0.7, 2)]):
            (tw, thh), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, sc, th)
            cv2.putText(img, s, (o[0] - tw // 2, o[1] + dy), cv2.FONT_HERSHEY_SIMPLEX, sc, (20, 20, 20), th)

    for it in g["doors"] + g["windows"]:
        a, b = P(it["opening_m"][0]), P(it["opening_m"][1])
        col = CLR.get(it["type"], (0, 0, 0))
        cv2.line(img, a, b, col, 10)
        mx, my = (a[0] + b[0]) // 2, (a[1] + b[1]) // 2
        lab = f"{it['id']} {it['type']} {it['width_m']:.2f}"
        (tw, th), _ = cv2.getTextSize(lab, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (mx - tw // 2 - 4, my - th - 26), (mx + tw // 2 + 6, my - 14), (255, 255, 255), -1)
        cv2.putText(img, lab, (mx - tw // 2, my - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    return img


def main():
    img = render()
    if sys.argv[1] == "full":
        out = os.path.join(DATA, "v6", "clean_full.png")
        cv2.imwrite(out, img)
        print("write", out, img.shape)
        return
    out = sys.argv[2]
    mx0, my0, mx1, my1 = (float(v) for v in sys.argv[3:7])
    zoom = float(sys.argv[7]) if len(sys.argv) > 7 else 4.0
    c = img[int(my0 * PP):int(my1 * PP), int(mx0 * PP):int(mx1 * PP)]
    c = cv2.resize(c, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(out, c)
    print("write", out, c.shape)


main()
