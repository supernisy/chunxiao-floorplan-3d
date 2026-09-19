"""Debug: polygonize wall lines, show all faces colored by area/compactness."""
import json, math, os
from collections import defaultdict
from shapely import LineString, MultiLineString, unary_union, polygonize

ROOT = os.path.join(os.path.dirname(__file__), "..")
LAYER = os.path.join(ROOT, "data", "layers.json")
OUT_SVG = os.path.join(ROOT, "data", "debug_polys.svg")

with open(LAYER, "r", encoding="utf-8") as f:
    layers = json.load(f)

def snap(v, tol=0.3):
    return round(v/tol)*tol

def snap_seg(item):
    (x0,y0),(x1,y1) = item["pts"]
    a = (snap(x0), snap(y0))
    b = (snap(x1), snap(y1))
    return (a,b) if a!=b else None

WALL_LAYERS = ["P-WALL", "A-通-墙...........COMM-WALL"]
segs = []
for layer in WALL_LAYERS:
    for item in layers.get(layer, []):
        if item["kind"] == "line":
            s = snap_seg(item)
            if s: segs.append(s)

mls = MultiLineString([LineString(s) for s in segs])
unioned = unary_union(mls)
print(f"unioned type={unioned.geom_type}")
geoms = list(unioned.geoms) if hasattr(unioned, "geoms") else [unioned]
poly_coll = polygonize(geoms)
polys = list(poly_coll.geoms)
print(f"segs={len(segs)} polys={len(polys)}")

faces = []
for p in polys:
    area = p.area
    bbox = p.bounds
    w = bbox[2]-bbox[0]; h = bbox[3]-bbox[1]
    compact = area/(w*h) if w*h>0 else 0
    faces.append({"poly":p,"area":area,"compact":compact,"bounds":bbox})
faces.sort(key=lambda f: -f["area"])

print("\nTOP 30 areas (pt^2):")
for f in faces[:30]:
    print(f"  area={f['area']:.1f} compact={f['compact']:.3f} bounds={f['bounds']}")
print("\nBOTTOM 20 areas:")
for f in faces[-20:]:
    print(f"  area={f['area']:.3f} compact={f['compact']:.3f}")

# SVG
xs = [c for s in segs for c in [s[0][0],s[1][0]]]
ys = [c for s in segs for c in [s[0][1],s[1][1]]]
minx, maxx, miny, maxy = min(xs)-10, max(xs)+10, min(ys)-10, max(ys)+10
W, H = maxx-minx, maxy-miny

# color map: log area
import math as m
areas = [f["area"] for f in faces]
amin, amax = max(1, min(areas)), max(areas)
def color(a):
    if a < 100: return "#ffcccc"
    if a < 500: return "#ff9999"
    if a < 1500: return "#ffcc66"
    if a < 4000: return "#99cc66"
    if a < 10000: return "#66ccff"
    return "#9999ff"

lines = []
lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {W} {H}" width="{W*1.2}" height="{H*1.2}">')
for f in faces:
    coords = list(f["poly"].exterior.coords)
    pts = " ".join(f"{x},{y}" for x,y in coords)
    lines.append(f'<polygon points="{pts}" fill="{color(f["area"])}" stroke="#333" stroke-width="0.3" opacity="0.65"/>')
# draw wall centerlines
for s in segs[:2000]:
    lines.append(f'<line x1="{s[0][0]}" y1="{s[0][1]}" x2="{s[1][0]}" y2="{s[1][1]}" stroke="black" stroke-width="0.2"/>')
lines.append('</svg>')
with open(OUT_SVG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"WROTE {OUT_SVG}")
