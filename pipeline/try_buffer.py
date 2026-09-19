"""Try buffering wall lines (as centerlines) by various half-thicknesses and see
if we get room polygons as the interior holes of the wall union.
"""
import json, os
from shapely import LineString, MultiLineString, unary_union, Polygon

ROOT = os.path.join(os.path.dirname(__file__), "..")
LAYER = os.path.join(ROOT, "data", "layers.json")
SCALE = os.path.join(ROOT, "data", "scale.json")

with open(LAYER) as f: layers = json.load(f)
with open(SCALE) as f: scale = json.load(f)
m_per_pt = scale["scale_m_per_point"]

def snap(v, tol=0.3): return round(v/tol)*tol

segs = []
for item in layers.get("P-WALL", []):
    if item["kind"] != "line": continue
    (x0,y0),(x1,y1) = item["pts"]
    a = (snap(x0), snap(y0)); b = (snap(x1), snap(y1))
    if a != b: segs.append((a,b))

mls = MultiLineString([LineString(s) for s in segs])
unioned = unary_union(mls)

for half_m in [0.10, 0.15, 0.20]:
    half_pt = half_m / m_per_pt
    buffered = unioned.buffer(half_pt)
    walls_union = unary_union(buffered)
    print(f"\nhalf={half_m}m ({half_pt:.1f}pt) union type={walls_union.geom_type}")
    if walls_union.geom_type == "Polygon":
        print(f"  area={walls_union.area:.0f} pt^2  interiors={len(walls_union.interiors)}")
        areas = sorted([Polygon(ring).area for ring in walls_union.interiors], reverse=True)
        print(f"  top 10 room areas pt^2: {areas[:10]}")
    elif walls_union.geom_type == "MultiPolygon":
        total_area = sum(p.area for p in walls_union.geoms)
        print(f"  total_area={total_area:.0f} pt^2 polys={len(walls_union.geoms)}")
        for i, p in enumerate(walls_union.geoms):
            areas = sorted([Polygon(ring).area for ring in p.interiors], reverse=True)
            print(f"    poly{i} interiors={len(p.interiors)} top areas={areas[:5]}")
