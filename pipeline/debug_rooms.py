"""Debug overlay of segmented room polygons on the rendered plan."""
import json, os, random
import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
IMG = os.path.join(ROOT, "data", "plan.png")
GRAPH = os.path.join(ROOT, "data", "room-graph.json")
OUT = os.path.join(ROOT, "data", "debug_rooms.png")

img = cv2.imread(IMG)
overlay = img.copy()
ZOOM = 2.2

with open(GRAPH) as f:
    graph = json.load(f)

rooms = graph["rooms"]
rooms.sort(key=lambda r: -r["area_m2"])
for i, r in enumerate(rooms):
    pts = np.array(r["polygon_px"], dtype=np.int32).reshape(-1, 1, 2)
    col = (random.randint(80,255), random.randint(80,255), random.randint(80,255))
    cv2.polylines(overlay, [pts], True, col, 2)
    cx, cy = r["centroid_pt"]
    cx_px = int(cx * ZOOM); cy_px = int(cy * ZOOM)
    cv2.putText(overlay, f"{i}:{r['area_m2']}", (cx_px, cy_px), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)

cv2.imwrite(OUT, overlay)
print(f"WROTE {OUT}")
