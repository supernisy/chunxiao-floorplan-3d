"""按 (图层, 颜色) 分别栅格化 CAD 矢量元素，用于判定「哪些颜色才是墙」。

坐标: m -> pt = m * 45.36 ; pt -> px = pt * (PP / 45.36)
用法:
  python pipeline/raster_layers.py                       # 导出全部 (图层,颜色) 掩膜 + 彩色总览
  python pipeline/raster_layers.py --spec out.png "P-WALL#FF00FF" "COLUWL-HATCH#808080"
"""
import os, sys, json, re
import numpy as np
import cv2

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
PT_PER_M = 45.36
PP = 200.0                      # px per meter
PAGE_W, PAGE_H = 1191.0, 842.0  # pt

def load():
    return json.load(open(os.path.join(DATA, "layers.json"), encoding="utf-8"))

def to_px(p):
    return (p[0] / PT_PER_M * PP, p[1] / PT_PER_M * PP)

def canvas():
    return np.zeros((int(PAGE_H / PT_PER_M * PP) + 2, int(PAGE_W / PT_PER_M * PP) + 2), np.uint8)

def draw(it, img, thick_px=None):
    pts = it.get("pts") or []
    if len(pts) < 2:
        return
    px = np.array([[int(round(v)) for v in to_px(p)] for p in pts], np.int32)
    w = thick_px
    if w is None:
        wpt = it.get("width") or 0.72
        w = max(2, int(round(wpt / PT_PER_M * PP)))
    if it["kind"] == "poly":
        cv2.fillPoly(img, [px], 255)
        cv2.polylines(img, [px], True, 255, max(1, w // 2))
    else:
        cv2.polylines(img, [px], False, 255, max(1, w // 2), cv2.LINE_8)

def masks_by_group(layers, keys=None):
    out = {}
    for ln, items in layers.items():
        for it in items:
            c = it.get("color") or "None"
            key = (ln, c)
            if keys is not None and f"{ln}#{c}" not in keys:
                continue
            if key not in out:
                out[key] = canvas()
            draw(it, out[key])
    return out

def main():
    layers = load()
    args = sys.argv[1:]
    if args and args[0] == "--spec":
        out_name = args[1]
        keys = set(args[2:])
        m = masks_by_group(layers, keys)
        img = canvas()
        for mk, mv in m.items():
            img = np.maximum(img, mv)
        out = os.path.join(DATA, out_name)
        cv2.imwrite(out, img)
        print("SAVED", out, img.shape, "groups:", list(m.keys()))
        return

    # 全量：每组存单独掩膜，并生成彩色总览
    groups = {}
    for ln, items in layers.items():
        for it in items:
            c = it.get("color") or "None"
            groups.setdefault((ln, c), None)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255),
               (0, 255, 255), (128, 0, 255), (0, 128, 255), (128, 255, 0), (255, 128, 0),
               (0, 0, 128), (128, 128, 0), (0, 128, 0), (128, 0, 0), (64, 64, 64)]
    overview = np.zeros((int(PAGE_H / PT_PER_M * PP) + 2, int(PAGE_W / PT_PER_M * PP) + 2, 3), np.uint8)
    os.makedirs(os.path.join(DATA, "masks"), exist_ok=True)
    for i, key in enumerate(sorted(groups)):
        m = masks_by_group(layers, {f"{key[0]}#{key[1]}"})
        mv = m[key]
        safe = re.sub(r"[^0-9A-Za-z]+", "_", f"{key[0]}_{key[1]}")[:60]
        cv2.imwrite(os.path.join(DATA, "masks", safe + ".png"), mv)
        col = palette[i % len(palette)]
        overview[mv > 0] = col
        print(f"{safe:64s} px={int((mv>0).sum()):8d} color={key[1]}")
    cv2.imwrite(os.path.join(DATA, "masks_overview.png"), overview)
    print("SAVED overview ->", os.path.join(DATA, "masks_overview.png"))

if __name__ == "__main__":
    main()
