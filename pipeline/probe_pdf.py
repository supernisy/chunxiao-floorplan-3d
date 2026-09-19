"""Layer-0 probe: inspect CAD-exported PDF vector geometry.
Writes a structured report to ../data/probe_report.txt and raw json to ../data/probe_raw.json
"""
import sys, os, json, collections
import fitz  # PyMuPDF

SRC = os.path.join(os.path.dirname(__file__), "..", "assets", "chunxiao.pdf")
OUT_TXT = os.path.join(os.path.dirname(__file__), "..", "data", "probe_report.txt")
OUT_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "probe_raw.json")

def rgb(t):
    if t is None:
        return None
    return tuple(round(c, 3) for c in t)

doc = fitz.open(SRC)
report = []
report.append(f"PDF path: {os.path.abspath(SRC)}")
report.append(f"page count: {doc.page_count}")
report.append(f"OCGs (layers) at doc level: {doc.get_ocgs()}")

prim_counts = collections.Counter()
color_layer = collections.Counter()   # (color_hex, layer) -> count
color_hex_counter = collections.Counter()
layer_counter = collections.Counter()
widths = collections.Counter()
all_items = 0
sample_items = []
drawings_bbox = None

for pno in range(doc.page_count):
    page = doc[pno]
    report.append(f"\n--- page {pno} rect={page.rect} rotation={page.rotation} ---")
    # try layers API
    try:
        layers = page.get_layers()
        report.append(f"page.get_layers(): {layers}")
    except Exception as e:
        report.append(f"page.get_layers() err: {e}")
    drawings = page.get_drawings()
    report.append(f"drawings count: {len(drawings)}")
    for d in drawings:
        items = d.get("items", [])
        color = rgb(d.get("color"))
        layer = d.get("layer")
        width = d.get("width")
        fill = rgb(d.get("fill"))
        prim_counts[d.get("type")] += 1
        color_hex = None if color is None else "#%02X%02X%02X" % tuple(int(c*255) for c in color)
        if color_hex:
            color_hex_counter[color_hex] += 1
        if layer:
            layer_counter[layer] += 1
        color_layer[(color_hex, layer)] += 1
        if width is not None:
            widths[round(width, 2)] += 1
        all_items += len(items)
        r = d.get("rect")
        if r is not None:
            if drawings_bbox is None:
                drawings_bbox = fitz.Rect(r)
            else:
                drawings_bbox |= r
        if len(sample_items) < 40:
            sample_items.append({
                "type": d.get("type"),
                "color": color_hex,
                "fill": "#%02X%02X%02X" % tuple(int(c*255) for c in fill) if fill else None,
                "width": width,
                "layer": layer,
                "rect": [round(x,1) for x in (r.x0,r.y0,r.x1,r.y1)] if r else None,
                "n_items": len(items),
            })

report.append(f"\nTOTAL primitive items: {all_items}")
report.append(f"drawings bbox (points): {drawings_bbox}")
report.append("\n--- primitive type counts ---")
for k,v in prim_counts.most_common():
    report.append(f"  {k}: {v}")
report.append("\n--- distinct stroke colors (hex) ---")
for c,n in color_hex_counter.most_common(40):
    report.append(f"  {c}: {n}")
report.append("\n--- distinct layers (OCG) ---")
for l,n in layer_counter.most_common(60):
    report.append(f"  {l}: {n}")
report.append("\n--- (color,layer) combos top 60 ---")
for (c,l),n in color_layer.most_common(60):
    report.append(f"  color={c} layer={l} : {n}")
report.append("\n--- line widths top 30 ---")
for w,n in widths.most_common(30):
    report.append(f"  w={w}: {n}")
report.append("\n--- sample drawings (first 40) ---")
for s in sample_items:
    report.append(f"  {s}")

txt = "\n".join(report)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(txt)
# raw json: keep a capped subset for detailed inspection
raw = {
    "page_count": doc.page_count,
    "drawings_bbox_points": list(drawings_bbox) if drawings_bbox else None,
    "color_hex_counter": dict(color_hex_counter),
    "layer_counter": dict(layer_counter),
    "color_layer": {f"{c}|{l}": n for (c,l),n in color_layer.items()},
    "widths": {str(k): v for k,v in widths.items()},
    "sample": sample_items,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False, indent=2)
print("PROBE_DONE")
print(txt)
