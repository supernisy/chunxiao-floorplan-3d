"""roi_pdf.py — 渲染指定 ROI 的 PDF 原图，并按图层语义高亮，用于人工判读。

用法: python pipeline/roi_pdf.py X0 Y0 X1 Y1 [scale] [out.png]
"""
import os, sys, json
import numpy as np, cv2, pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import geom_v5 as G5

ROOT = os.path.join(HERE, "..")
V6 = os.path.join(ROOT, "data", "v6")
PT = 45.36

WALL_LAYERS = ["P-WALL", "A-通-墙...........COMM-WALL",
               "S-柱墙-模板线.....COLUWL-LINE1", "S-柱墙-填充.......COLUWL-HATCH"]
FIN_LAYER = "P-WALL FIN"
DOOR_LAYER = "P-DOOR"
GLASS_LAYER = "A-通-门窗剖线.....COMM-GLAZ-SECT"


def main():
    x0, y0, x1, y1 = (float(v) for v in sys.argv[1:5])
    scale = float(sys.argv[5]) if len(sys.argv) > 5 else 300.0
    outp = sys.argv[6] if len(sys.argv) > 6 else os.path.join(V6, "roi_pdf.png")

    doc = pymupdf.open(os.path.join(ROOT, "assets", "chunxiao.pdf"))
    pg = doc[0]
    clip = pymupdf.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT)
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(scale / PT, scale / PT),
                        colorspace=pymupdf.csRGB, alpha=False, clip=clip)
    base = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    img = cv2.cvtColor(base, cv2.COLOR_RGB2BGR)

    Wp, Hp = pix.width, pix.height

    def to_px(p):
        return (int(round((p.x / PT - x0) * scale)), int(round((p.y / PT - y0) * scale)))

    # 高亮各语义层（设 PLAIN=1 则只看原图，便于判读真实墙面填充）
    spec = [] if os.environ.get("PLAIN") else [
        (WALL_LAYERS, (0, 0, 255), 3),      # 结构墙 -> 红
        ([FIN_LAYER], (255, 0, 255), 2),    # 面层 -> 品红
        ([DOOR_LAYER], (0, 165, 255), 3),   # 门 -> 橙
        ([GLASS_LAYER], (0, 200, 0), 3)]    # 玻璃 -> 绿
    for names, col, th in spec:
        for nm in names:
            for it in G5.LAYERS.get(nm, []):
                pts = it.get("pts") or []
                if len(pts) < 2:
                    continue
                if it.get("kind") == "poly":
                    arr = np.array([to_px(pymupdf.Point(p[0], p[1])) for p in pts], np.int32)
                    cv2.polylines(img, [arr], True, col, th, cv2.LINE_8)
                else:
                    for i in range(len(pts) - 1):
                        cv2.line(img, to_px(pymupdf.Point(*pts[i])),
                                 to_px(pymupdf.Point(*pts[i + 1])), col, th, cv2.LINE_8)

    # 网格
    import math
    g = math.floor(x0 / 0.25) * 0.25
    while g <= x1:
        px = int((g - x0) * scale)
        cv2.line(img, (px, 0), (px, Hp), (210, 210, 210), 1)
        cv2.putText(img, f"{g:g}", (px + 3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 60, 200), 1)
        g = round(g + 0.25, 4)
    g = math.floor(y0 / 0.25) * 0.25
    while g <= y1:
        py = int((g - y0) * scale)
        cv2.line(img, (0, py), (Wp, py), (210, 210, 210), 1)
        cv2.putText(img, f"{g:g}", (4, py + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 60, 200), 1)
        g = round(g + 0.25, 4)

    cv2.imwrite(outp, img)
    print("SAVED", outp, img.shape)


if __name__ == "__main__":
    main()
