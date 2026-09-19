"""verify_overlay.py — 把重建结果叠到 PDF 原图上做「一眼验证」。

叠三层：
  房间多边形轮廓 + 房名（浅绿描边 / 白字黑底）
  墙多边形（橙色，可见墙与房间的贴合关系）
  洞口按类型着色：swing=红 / sliding=蓝（玻璃移门）/ window=青

用法:
  python pipeline/verify_overlay.py full
  python pipeline/verify_overlay.py crop out.png mx0 my0 mx1 my1 [zoom]
"""
import os, sys, json
import numpy as np, cv2, fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
APP = os.path.join(ROOT, "app", "src", "data")
PDF = os.path.join(ROOT, "assets", "chunxiao.pdf")
PT_PER_M, PP = 45.36, 200.0

CLR = {"swing": (0, 0, 230), "sliding": (255, 100, 0), "window": (200, 200, 0)}


def base_pdf():
    doc = fitz.open(PDF)
    mm = PP / PT_PER_M
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(mm, mm), colorspace=fitz.csRGB, alpha=False)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def draw(img):
    g = json.load(open(os.path.join(APP, "room-graph.json"), encoding="utf-8"))
    walls = json.load(open(os.path.join(APP, "walls_poly.json"), encoding="utf-8"))

    def P(p):
        return (int(round(p[0] * PP)), int(round(p[1] * PP)))

    for w in walls:
        cv2.polylines(img, [np.array([P(p) for p in w["shell"]], np.int32)], True, (0, 90, 255), 3)
    for r in g["rooms"]:
        cv2.polylines(img, [np.array([P(p) for p in r["polygon_m"]], np.int32)], True, (0, 200, 0), 2)
        cx = sum(p[0] for p in r["polygon_m"]) / len(r["polygon_m"])
        cy = sum(p[1] for p in r["polygon_m"]) / len(r["polygon_m"])
        t = f"{r['name']} {r['area_m2']}"
        (tw, th), _ = cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        o = P((cx, cy))
        cv2.rectangle(img, (o[0] - 4, o[1] - th - 4), (o[0] + tw + 4, o[1] + 6), (30, 30, 30), -1)
        cv2.putText(img, t, (o[0], o[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    for it in g["doors"] + g["windows"]:
        a, b = P(it["opening_m"][0]), P(it["opening_m"][1])
        col = CLR.get(it["type"], (255, 255, 255))
        cv2.line(img, a, b, col, 8)
        mid = ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2)
        cv2.putText(img, f"{it['id']}", (mid[0] - 18, mid[1] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(img, f"{it['id']}", (mid[0] - 18, mid[1] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1)
    return img


def main():
    img = draw(base_pdf())
    if sys.argv[1] == "full":
        out = os.path.join(DATA, "v6", "verify_full.png")
        s = 0.85
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        cv2.imwrite(out, img)
        print("write", out, img.shape)
        return
    out = sys.argv[2]
    mx0, my0, mx1, my1 = (float(v) for v in sys.argv[3:7])
    zoom = float(sys.argv[7]) if len(sys.argv) > 7 else 4.0
    x0, y0 = int(mx0 * PP), int(my0 * PP)
    x1, y1 = int(mx1 * PP), int(my1 * PP)
    c = img[max(0, y0):y1, max(0, x0):x1]
    c = cv2.resize(c, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(out, c)
    print("write", out, c.shape)


main()
