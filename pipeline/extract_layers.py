"""Layer-1 extraction: pull vector primitives per semantic layer from the CAD PDF.
Skips the huge furniture-fill layers (not needed for a bare-shell model).
Writes:
  ../data/layers.json   -> { layer: [ {kind, pts, color, width}, ... ] }
  ../data/text.json     -> [ {text, x0,y0,x1,y1, size, color}, ... ]
Coordinates are in PDF points (y down). Units unknown until scale step.
"""
import os, json
import fitz

SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT_LAYERS = os.path.join(os.path.dirname(__file__), "..", "data", "layers.json")
OUT_TEXT = os.path.join(os.path.dirname(__file__), "..", "data", "text.json")

# Layers we actually need for a bare-shell rebuild. Anything furniture/hatch-heavy is skipped.
TARGET_LAYERS = {
    "P-WALL", "A-通-墙...........COMM-WALL", "户型刷图层$0$A-WALL-FNSH",
    "S-柱墙-填充.......COLUWL-HATCH", "S-柱墙-模板线.....COLUWL-LINE1",
    "P-WALL FIN", "A-通-门窗剖线.....COMM-GLAZ-SECT", "P-DOOR",
    "A-平-楼梯.........FLOR-STAIR", "A-平-栏杆扶手.....FLOR-RAIL",
    "P-TOILET", "I-FURNITURE-FIX", "A-平-家具.........FLOR-FURN",
    "H-Y   可移动家具", "H-Y   人物标注", "P-TUBE", "P-EQU-强弱电箱",
}
# Layers that carry dimension/room text for scale + labels
TEXT_LAYERS = {"P-TEXT", "P-DIM", "E-dim", "DIM_SYMB", "PUB_TITLE"}

def bezier(p0, p1, p2, p3, n=10):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = (u*u*u)*p0.x + 3*(u*u)*t*p1.x + 3*u*(t*t)*p2.x + (t*t*t)*p3.x
        y = (u*u*u)*p0.y + 3*(u*u)*t*p1.y + 3*u*(t*t)*p2.y + (t*t*t)*p3.y
        pts.append([round(x, 2), round(y, 2)])
    return pts

def hexc(t):
    if t is None:
        return None
    return "#%02X%02X%02X" % tuple(int(c*255) for c in t)

doc = fitz.open(SRC)
page = doc[0]
drawings = page.get_drawings()

layers = {}   # name -> list of primitives
for d in drawings:
    layer = d.get("layer")
    if layer not in TARGET_LAYERS:
        continue
    color = hexc(d.get("color"))
    width = d.get("width")
    for it in d.get("items", []):
        op = it[0]
        if op == "l":
            p1, p2 = it[1], it[2]
            layers.setdefault(layer, []).append({
                "kind": "line", "pts": [[round(p1.x,2),round(p1.y,2)],[round(p2.x,2),round(p2.y,2)]],
                "color": color, "width": width})
        elif op == "re":
            r = it[1]
            corners = [[r.x0,r.y0],[r.x1,r.y0],[r.x1,r.y1],[r.x0,r.y1],[r.x0,r.y0]]
            layers.setdefault(layer, []).append({"kind":"poly","pts":corners,"color":color,"width":width})
        elif op == "qu":
            q = it[1]
            try:
                corners = [q.ul, q.ur, q.lr, q.ll]
            except Exception:
                r = q.rect
                corners = [r.top_left, r.top_right, r.bottom_right, r.bottom_left]
            pts = [[round(p.x,2),round(p.y,2)] for p in corners]
            layers.setdefault(layer, []).append({"kind":"poly","pts":pts+[pts[0]],"color":color,"width":width})
        elif op == "c":
            p0,p1,p2,p3 = it[1],it[2],it[3],it[4]
            pts = bezier(p0,p1,p2,p3)
            layers.setdefault(layer, []).append({"kind":"curve","pts":pts,"color":color,"width":width})

# text extraction (all text, with bbox + size). Associate to layer loosely by position later.
texts = []
tdict = page.get_text("dict")
for block in tdict.get("blocks", []):
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            txt = span.get("text", "").strip()
            if not txt:
                continue
            bb = span.get("bbox")
            texts.append({
                "text": txt,
                "x0": round(bb[0],2), "y0": round(bb[1],2),
                "x1": round(bb[2],2), "y1": round(bb[3],2),
                "size": round(span.get("size",0),2),
                "color": hexc(span.get("color")),
            })

with open(OUT_LAYERS, "w", encoding="utf-8") as f:
    json.dump(layers, f, ensure_ascii=False)

# compact summary
summary = {k: len(v) for k, v in layers.items()}
summary_text = {"n_text": len(texts), "sample": texts[:30]}
with open(OUT_LAYERS + ".summary.txt", "w", encoding="utf-8") as f:
    f.write("LAYER PRIMITIVE COUNTS\n")
    for k, v in sorted(summary.items(), key=lambda x:-x[1]):
        f.write(f"  {k}: {v}\n")
    f.write(f"\nTEXT count: {len(texts)}\n")
    f.write("SAMPLE TEXT:\n")
    for t in texts[:40]:
        f.write(f"  '{t['text']}' @ ({t['x0']},{t['y0']})-({t['x1']},{t['y1']}) size={t['size']} color={t['color']}\n")

with open(OUT_TEXT, "w", encoding="utf-8") as f:
    json.dump(texts, f, ensure_ascii=False)

print("EXTRACT_DONE layers=%d text=%d" % (len(layers), len(texts)))
