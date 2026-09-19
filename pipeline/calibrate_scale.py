"""Layer-2 scale calibration.
The PDF stores dimension text as vector outlines (not extractable glyphs).
We read the overall top width from the rendered dimension bar as 15000 mm,
then find the corresponding top horizontal dimension line in P-DIM geometry
and compute points -> meters scale.
"""
import json, math, os
ROOT = os.path.join(os.path.dirname(__file__), "..")
LAYER = os.path.join(ROOT, "data", "layers.json")
OUT = os.path.join(ROOT, "data", "scale.json")

with open(LAYER, "r", encoding="utf-8") as f:
    layers = json.load(f)

# PDF text is vector-outlined -> we read the overall top width visually from
# clip_top_dims.png as 15000 mm (7200+1800+3900+2100).
# Instead of trying to locate the exact dimension line (it may be split/OCG-mapped),
# we use the outer wall envelope from the wall layers as the geometric proxy for
# that 15000 mm overall width.
WALL_LAYERS = ["P-WALL", "A-通-墙...........COMM-WALL",
               "S-柱墙-填充.......COLUWL-HATCH", "S-柱墙-模板线.....COLUWL-LINE1"]
xs, ys = [], []
for layer in WALL_LAYERS:
    for item in layers.get(layer, []):
        if item["kind"] != "line":
            continue
        for p in item["pts"]:
            xs.append(p[0]); ys.append(p[1])
min_x, max_x = min(xs), max(xs)
min_y, max_y = min(ys), max(ys)
width_pt = max_x - min_x
height_pt = max_y - min_y

TOTAL_MM = 15000   # overall building width, read visually from top dim bar
scale_mm_per_pt = TOTAL_MM / width_pt
scale_m_per_pt = scale_mm_per_pt / 1000.0

result = {
    "method": "wall_envelope_vs_overall_width",
    "total_width_mm": TOTAL_MM,
    "wall_envelope_points": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y,
                             "width_pt": width_pt, "height_pt": height_pt},
    "scale_mm_per_point": round(scale_mm_per_pt, 4),
    "scale_m_per_point": round(scale_m_per_pt, 6),
    "points_per_meter": round(1.0/scale_m_per_pt, 3),
    "derived_height_mm": round(height_pt * scale_mm_per_pt),
    "derived_height_m": round(height_pt * scale_m_per_pt, 2),
    "confidence": "medium",
    "note": "Text vector-outlined; total width 15000 mm read visually from clip_top_dims.png; envelope from wall layers."
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("SCALE", result)
