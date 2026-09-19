"""Layer-1/Layer-3 fallback: use raster image segmentation on the rendered plan
because vector polygonization of double-line walls did not close rooms cleanly.

We pick wall-colored pixels (blue/magenta/yellow), dilate to close gaps, invert
to get room candidates, then extract connected components as room polygons.
Coordinates are converted back from image pixels -> PDF points -> meters.
"""
import json, os, math
import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
IMG = os.path.join(ROOT, "data", "plan.png")
SCALE = os.path.join(ROOT, "data", "scale.json")
OUT = os.path.join(ROOT, "data", "room-graph.json")

ZOOM = 2.2

with open(SCALE) as f:
    scale = json.load(f)
m_per_pt = scale["scale_m_per_point"]

img = cv2.imread(IMG)
if img is None:
    raise FileNotFoundError(IMG)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Wall colors in this CAD export (empirically tuned)
# Blue structural/partition walls
mask_blue = cv2.inRange(hsv, np.array([100, 80, 100]), np.array([130, 255, 255]))
# Magenta wall lines
mask_magenta1 = cv2.inRange(hsv, np.array([140, 80, 100]), np.array([179, 255, 255]))
mask_magenta2 = cv2.inRange(hsv, np.array([0, 80, 100]), np.array([10, 255, 255]))
# Yellow structural wall fills (COMM-WALL)
mask_yellow = cv2.inRange(hsv, np.array([15, 100, 120]), np.array([40, 255, 255]))
# Dark lines (outer walls, text, some dims) - keep only very dark low-saturation
mask_black = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 60, 80]))

wall_mask = cv2.bitwise_or(mask_blue, mask_magenta1)
wall_mask = cv2.bitwise_or(wall_mask, mask_magenta2)
wall_mask = cv2.bitwise_or(wall_mask, mask_yellow)
wall_mask = cv2.bitwise_or(wall_mask, mask_black)

# Morphological close to bridge small gaps in wall lines, then dilate to form solid walls
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
wall_closed = cv2.morphologyEx(wall_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
wall_dilated = cv2.dilate(wall_closed, kernel, iterations=2)

# Room mask: not wall, inside image
room_mask = cv2.bitwise_not(wall_dilated)
# Clean small speckles inside rooms
room_mask = cv2.morphologyEx(room_mask, cv2.MORPH_OPEN, kernel, iterations=1)

# Connected components of room mask
num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(room_mask, connectivity=4)
print(f"components (incl background): {num_labels}")

h, w = img.shape[:2]
areas_px = stats[:, cv2.CC_STAT_AREA]
order = np.argsort(-areas_px)
print("top component areas (px):", areas_px[order[:10]])

# Keep components: skip the largest (outside), keep only real rooms (>1500 px ~ >1 m2 at this zoom/scale).
MIN_ROOM_PX = 2000
keep_labels = []
outside_skipped = False
for idx in order:
    area = int(areas_px[idx])
    if area < MIN_ROOM_PX:
        continue
    if not outside_skipped:
        print(f"skipping largest component {idx} area={area} as outside")
        outside_skipped = True
        continue
    keep_labels.append(idx)

print(f"keeping {len(keep_labels)} room components")

rooms = []
for lab in keep_labels:
    # Extract binary mask for this component
    comp_mask = (labels == lab).astype(np.uint8) * 255
    # Find external contour
    contours, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        continue
    cnt = max(contours, key=cv2.contourArea)
    # Simplify polygon
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.01 * peri, True)
    pts_px = approx.reshape(-1, 2).tolist()
    # Convert px -> PDF points -> meters
    pts_pt = [[x/ZOOM, y/ZOOM] for x,y in pts_px]
    pts_m = [[round(x*m_per_pt,3), round(y*m_per_pt,3)] for x,y in pts_pt]
    cx_px, cy_px = centroids[lab]
    area_m2 = round((areas_px[lab] / (ZOOM*ZOOM)) * m_per_pt * m_per_pt, 2)
    rooms.append({
        "id": f"room_{lab}",
        "polygon_px": pts_px,
        "polygon_pt": pts_pt,
        "polygon_m": pts_m,
        "centroid_pt": [round(cx_px/ZOOM,2), round(cy_px/ZOOM,2)],
        "area_m2": area_m2,
        "label": ""
    })

rooms.sort(key=lambda r: -r["area_m2"])
for i, r in enumerate(rooms):
    r["id"] = f"room_{i}"

graph = {
    "scale": scale,
    "rooms": rooms,
    "walls": [],
    "doors": [],
    "fixtures": [],
    "room_adjacency": [],
    "meta": {
        "method": "raster_segmentation_of_rendered_plan",
        "note": "Wall mask = blue+magenta+yellow; morphological close+diolate; rooms are connected components of inverted mask."
    }
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(graph, f, ensure_ascii=False, indent=2)

print(f"WROTE {OUT} with {len(rooms)} rooms")
for r in rooms[:15]:
    print(f"  {r['id']} area={r['area_m2']} m2")
