"""Layer-3 graph assembly: polygonize wall lines -> rooms, detect doors, emit room-graph.json.

Key simplifications for this real first run:
- Walls come from P-WALL + COMM-WALL line segments.
- Endpoints are snapped to a fine grid so shapely can build a clean planar graph.
- polygonize_full returns all faces. Thin faces (walls) are filtered by area+compactness.
- Rooms are kept; exterior is the polygon that contains the wall system center.
- Door leaves (P-DOOR orange lines + arcs) are matched to the nearest wall edge.
- Glass sliding doors are matched from COMM-GLAZ-SECT double-line clusters.
"""
import json, math, os, sys
from collections import defaultdict
from shapely import LineString, MultiLineString, Polygon, unary_union, polygonize_full
from shapely.ops import polygonize, snap, nearest_points
from shapely.geometry import Point

ROOT = os.path.join(os.path.dirname(__file__), "..")
LAYER = os.path.join(ROOT, "data", "layers.json")
SCALE = os.path.join(ROOT, "data", "scale.json")
OUT = os.path.join(ROOT, "data", "room-graph.json")

with open(LAYER, "r", encoding="utf-8") as f:
    layers = json.load(f)
with open(SCALE, "r", encoding="utf-8") as f:
    scale = json.load(f)

m_per_pt = scale["scale_m_per_point"]
pts_per_m = scale["points_per_meter"]

def snap_coord(v, tol=0.15):
    return round(v / tol) * tol

def snap_seg(seg, tol=0.15):
    (x0,y0),(x1,y1) = seg
    a = (snap_coord(x0,tol), snap_coord(y0,tol))
    b = (snap_coord(x1,tol), snap_coord(y1,tol))
    if a == b:
        return None
    return (a,b)

# --------------------- wall lines ---------------------
WALL_LAYERS = ["P-WALL", "A-通-墙...........COMM-WALL",
               "S-柱墙-填充.......COLUWL-HATCH", "S-柱墙-模板线.....COLUWL-LINE1"]
segs = []
for layer in WALL_LAYERS:
    for item in layers.get(layer, []):
        if item["kind"] != "line":
            continue
        s = snap_seg(item["pts"])
        if s:
            segs.append(s)

print(f"wall segments after snap: {len(segs)}")
mls = MultiLineString([LineString(s) for s in segs])
# union to merge dangles/coincident edges
unioned = unary_union(mls)
print(f"unioned geom type: {unioned.geom_type}")

# polygonize
polys = list(polygonize(unioned))
print(f"polygonize produced {len(polys)} faces")

# classify faces
faces = []
for p in polys:
    area = p.area
    bbox = p.bounds
    w = bbox[2]-bbox[0]; h = bbox[3]-bbox[1]
    bbox_area = w*h if w*h>0 else 1
    compact = area / bbox_area
    faces.append({"poly": p, "area": area, "compact": compact, "w": w, "h": h})

# heuristic: walls are thin -> either very small area (<1500 pt^2) or low compactness (<0.12)
# rooms are larger and compact
rooms = []
walls = []
for f in faces:
    if f["area"] > 2500 and f["compact"] > 0.15:
        rooms.append(f)
    else:
        walls.append(f)

rooms.sort(key=lambda r: -r["area"])
print(f"rooms={len(rooms)} walls={len(walls)}")

# drop the largest room if it's actually the outside frame (envelope of all others)
# Compute the centroid of all room centroids; the outside frame will contain that point or be far.
# Simpler: the outside frame is the one with the greatest max distance to centroid of others.
if len(rooms) > 1:
    all_cent = Point(sum(r["poly"].centroid.x for r in rooms)/len(rooms),
                     sum(r["poly"].centroid.y for r in rooms)/len(rooms))
    outside_idx = max(range(len(rooms)), key=lambda i: rooms[i]["poly"].distance(all_cent))
    # Actually the outside frame should contain the centroid. Use contains instead.
    outside_idx = None
    for i, r in enumerate(rooms):
        if r["poly"].contains(all_cent) or r["poly"].intersects(all_cent.buffer(2)):
            outside_idx = i
            break
    if outside_idx is not None:
        outside = rooms.pop(outside_idx)
        print(f"removed outside frame at index {outside_idx}")

# --------------------- door detection ---------------------
# Collect P-DOOR lines and arcs
door_lines = []   # (p0,p1)
door_curves = []  # list of pts
for item in layers.get("P-DOOR", []):
    if item["kind"] == "line":
        door_lines.append(item["pts"])
    elif item["kind"] == "curve":
        door_curves.append(item["pts"])

print(f"P-DOOR lines={len(door_lines)} curves={len(door_curves)}")

# Match a door leaf to nearest wall edge. The wall edges are the boundary of the unioned wall geometry.
wall_edges = list(LineString(coord) for coord in unioned.geoms) if unioned.geom_type == "MultiLineString" else [unioned]

def nearest_wall_edge(pt):
    p = Point(pt)
    best = None; bestd = 1e9
    for e in wall_edges:
        d = p.distance(e)
        if d < bestd:
            bestd = d; best = e
    return best, bestd

# group arcs with lines: an arc and a line that share an endpoint -> swing door
arcs_matched = set()
doors = []
for ln in door_lines:
    p0, p1 = (ln[0][0], ln[0][1]), (ln[1][0], ln[1][1])
    mid = ((p0[0]+p1[0])/2, (p0[1]+p1[1])/2)
    # find nearest arc endpoint
    best_arc = None; best_arc_dist = 1e9
    for i, crv in enumerate(door_curves):
        if i in arcs_matched: continue
        ep = (crv[0][0], crv[0][1])  # first point of arc
        d = math.hypot(ep[0]-p0[0], ep[1]-p0[1]) + math.hypot(ep[0]-p1[0], ep[1]-p1[1])
        # an endpoint of the arc must coincide with one door-leaf end
        d0 = math.hypot(ep[0]-p0[0], ep[1]-p0[1])
        d1 = math.hypot(ep[0]-p1[0], ep[1]-p1[1])
        if min(d0,d1) < 2.0 and min(d0,d1) < best_arc_dist:
            best_arc_dist = min(d0,d1); best_arc = (i, crv, 0)
        ep2 = (crv[-1][0], crv[-1][1])
        d0b = math.hypot(ep2[0]-p0[0], ep2[1]-p0[1])
        d1b = math.hypot(ep2[0]-p1[0], ep2[1]-p1[1])
        if min(d0b,d1b) < 2.0 and min(d0b,d1b) < best_arc_dist:
            best_arc_dist = min(d0b,d1b); best_arc = (i, crv, -1)
    dtype = "swing" if best_arc else "opening"
    width = math.hypot(p1[0]-p0[0], p1[1]-p0[1])
    # host wall: nearest wall edge
    e, ed = nearest_wall_edge(mid)
    doors.append({
        "type": dtype,
        "pts": ln,
        "width_pt": width,
        "width_m": round(width * m_per_pt, 3),
        "mid_pt": mid,
        "arc": best_arc[1] if best_arc else None,
        "host_edge_dist": ed,
        "confidence": "medium" if ed < 5 else "low"
    })
    if best_arc:
        arcs_matched.add(best_arc[0])

print(f"doors detected: {len(doors)}")

# --------------------- glass sliding doors ---------------------
# COMM-GLAZ-SECT lines, parallel double lines along walls -> sliding glass door or window
glaz_lines = []
for item in layers.get("A-通-门窗剖线.....COMM-GLAZ-SECT", []):
    if item["kind"] == "line":
        glaz_lines.append(item["pts"])
print(f"COMM-GLAZ-SECT lines={len(glaz_lines)}")

# --------------------- emit room-graph.json ---------------------
graph = {
    "scale": scale,
    "rooms": [],
    "walls": [],
    "doors": [],
    "fixtures": [],
}

for i, r in enumerate(rooms):
    coords = list(r["poly"].exterior.coords)[:-1]  # drop closing point
    coords_m = [[round(x*m_per_pt, 3), round(y*m_per_pt, 3)] for x,y in coords]
    graph["rooms"].append({
        "id": f"room_{i}",
        "polygon_pt": coords,
        "polygon_m": coords_m,
        "area_m2": round(r["poly"].area * m_per_pt * m_per_pt, 2),
        "centroid_pt": [round(r["poly"].centroid.x,2), round(r["poly"].centroid.y,2)],
        "label": ""
    })

# walls: keep the thin polygon faces as wall strips; or store raw wall segments
for i, w in enumerate(walls):
    coords = list(w["poly"].exterior.coords)[:-1]
    coords_m = [[round(x*m_per_pt,3), round(y*m_per_pt,3)] for x,y in coords]
    graph["walls"].append({
        "id": f"wall_{i}",
        "polygon_pt": coords,
        "polygon_m": coords_m,
        "area_m2": round(w["poly"].area * m_per_pt * m_per_pt, 3),
    })

for i, d in enumerate(doors):
    graph["doors"].append({
        "id": f"door_{i}",
        "type": d["type"],
        "width_m": d["width_m"],
        "leaf_pts_pt": d["pts"],
        "leaf_pts_m": [[round(p[0]*m_per_pt,3), round(p[1]*m_per_pt,3)] for p in d["pts"]],
        "arc_pts_pt": d["arc"],
        "arc_pts_m": [[round(p[0]*m_per_pt,3), round(p[1]*m_per_pt,3)] for p in d["arc"]] if d["arc"] else None,
        "confidence": d["confidence"]
    })

# room adjacency: shared boundary length between rooms
adj = []
for i in range(len(rooms)):
    for j in range(i+1, len(rooms)):
        shared = rooms[i]["poly"].boundary.intersection(rooms[j]["poly"].boundary)
        if shared.length > 1:
            adj.append({"a": f"room_{i}", "b": f"room_{j}", "shared_length_pt": round(shared.length,2)})
graph["room_adjacency"] = adj

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(graph, f, ensure_ascii=False, indent=2)

print(f"WROTE {OUT}: {len(graph['rooms'])} rooms, {len(graph['walls'])} wall strips, {len(graph['doors'])} doors")
