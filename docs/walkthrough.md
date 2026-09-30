# IndoorNav — Complete Project Walkthrough

> **Project**: IFC → Indoor Navigation System
> **Last updated**: 2026-09-09
> **Status**: Phase 1 complete ✅ | Phase 2 complete ✅

---

## Big Picture — What Are We Building?

A system that takes an **IFC building file** (the architect's 3D model) and turns it into a
**smart indoor navigation system** — like Google Maps but for inside a building, using
CCTV cameras instead of GPS.

```
  Architect's IFC file
         │
         ▼
  [Python Pipeline]
         │
         ├──► 3D model  (view in browser or Blender)
         │
         └──► Navigation graph  (find shortest route room-to-room)
                      │
                      └──► CCTV crowd data  (avoid crowded paths)
```

---

## Phase 1 — IFC to 3D Model ✅

### What is IFC?
IFC (Industry Foundation Classes) is the standard file format used by architects and
engineers to describe buildings.  It contains:
- Every wall, door, window, slab, column, stair
- Their exact 3D geometry and position in the world
- Metadata: which floor they're on, their GUID, material, etc.

### What does Phase 1 do?

```
data/raw/building.ifc
       │
       │  src/load_ifc.py        -- open the file, read schema + metadata
       │  src/extract_geometry.py -- triangulate every element into vertices+faces
       │  src/export_model.py     -- write .obj, .glb, elements.json
       │  src/visualize.py        -- render a color-coded screenshot
       │
       ▼
outputs/
  model.obj        ← open in Blender or the web dashboard
  model.glb        ← open in any glTF viewer
  elements.json    ← GUID index for every element
  render.png       ← color-coded screenshot
```

### Verified result on `Grethes-hus-bok-2.ifc` (Norwegian house)

| Metric | Value |
|---|---|
| Schema | IFC2X3 |
| Building | Grethes hus |
| Storeys | 3 (basement + 2 floors) |
| Elements extracted | 162 |
| Elements failed | 0 |
| Building size | 44 m × 37 m × 10 m |
| Pipeline runtime | ~18 seconds |

### Color coding

Each IFC type gets a distinct color in the output:

| Color | IFC Type |
|---|---|
| Warm beige | Walls |
| Sky blue | Windows |
| Orange-brown | Doors |
| Steel blue | Columns |
| Cool grey | Slabs/floors |
| Orange | Site ground |
| Vivid blue | Spaces/rooms |

### Key technical detail — Axis correction

IFC uses **Z-up** coordinates (Z points to the sky).
Blender, Three.js, and glTF use **Y-up** (Y points to the sky).

We convert every vertex on export:
```
IFC vertex (x, y, z) → exported as (x, z, -y)
```
Without this, the building appears lying on its side.

---

## Phase 1 Tools — The Browser Dashboard ✅

We also built a **browser-based 3D viewer** (`dashboard/index.html`) so you can view
the model without installing Blender.

### How to open it
```
Double-click:  dashboard/index.html
Then drag:     outputs/model.obj  onto the viewport
```

### Features

| Feature | How |
|---|---|
| Orbit (rotate) | Left-click drag |
| Pan | Right-click drag |
| Zoom | Scroll wheel |
| **Walk mode (game-style)** | Click "Walk Mode" → WASD + mouse |
| Toggle IFC types | Click items in left sidebar |
| Toggle floors | Click storey toggles in sidebar |
| Wireframe | Top bar button |
| Screenshot | Top bar button |
| FPS counter | Top right |
| Cursor world coordinates | Bottom right |

---

## Phase 2 — Navigation Graph ✅

### Why a graph?

GPS doesn't work indoors.  Instead, we model the building as a **graph**:
- **Nodes** = rooms, corridors, lobbies (IfcSpace) + stairs (IfcStair)
- **Edges** = connections between adjacent spaces (via doors, stairs, proximity)
- **Weights** = walking distance × crowd penalty

Then we run **Dijkstra's algorithm** on this graph to find the shortest route.

### How we build the graph from IFC

```
IFC file
  │
  ├── All IfcSpace  ──────────► Nodes (one per room/corridor)
  ├── All IfcStair  ──────────► Nodes (one per staircase)
  └── All IfcDoor   ──────────► Edges (which two rooms does this door connect?)
```

**The hard part** — IFC doesn't always tell you which two rooms a door connects.
We use 3 methods, tried in order:

| Method | Works for | How |
|---|---|---|
| IfcRelSpaceBoundary | IFC4 | Explicit relationship in the file |
| Door proximity | IFC2X3 | Find the 2 nearest rooms to each door centroid |
| Shapely polygon intersection | Any | Buffer room footprints, check overlap |

### Result on our test building

```
Graph: 12 nodes, 18 edges, 3 connected components
  - 8 IfcSpace nodes (the rooms, numbered 1-8)
  - 4 IfcStair/StairFlight nodes
  - 6 door-proximity edges
  - 2 stair vertical edges
  - 14 Shapely adjacency edges (filling gaps)
```

### Finding a route

```python
route = find_route(G, source_guid, target_guid)

# Output:
ROUTE: Room 1  ->  Staircase Run 2
  START  [1. etasje]  Room 1
    01   [1. etasje]  Room 3   (via proximity)
    02   [1. etasje]  Room 6   (via IfcDoor)
  END    Stair:389268 Run 1
  Distance: 8.8 m  |  Est. time: 7s
```

### Graph outputs

| File | Use |
|---|---|
| `outputs/nav_graph.json` | Full graph data (nodes + edges) |
| `outputs/nav_graph.gexf` | Drag into Gephi to visualize the graph |
| `outputs/cameras.json` | Auto-generated camera positions |
| `outputs/route_result.json` | Last computed route |

---

## Phase 2 — CCTV Integration ✅

Each physical camera is modelled as a **cone in 3D space**:
- Position (x, y, z)
- Direction vector
- Field of view angle (default 90°)
- Coverage radius (default 8m)

We find which graph nodes (rooms) fall inside each camera's cone.

### Auto-generated cameras (for testing)

Since we don't have real cameras yet, the system auto-places cameras
above each room centroid (pointing straight down, like a ceiling camera).

```
4 cameras auto-generated:
  CAM_01  1. etasje Camera 1   → covers rooms 1, 2 + stair
  CAM_02  1. etasje Camera 2   → covers rooms 3, 4, 5, 6 + stair
  CAM_03  Camera 3             → covers rooms 1, 2, 3, 4
  CAM_04  Camera 4             → covers rooms 5, 6, 7, 8

Coverage: 10/12 nodes under surveillance
```

---

## Phase 2 — Crowd Detection ✅

The crowd detection module uses **YOLOv8** (a state-of-the-art object detector)
to count people in each camera frame.

### How it works

```
Camera frame (image)
       │
  [YOLOv8 detector]  ← looks for class 0 = "person" in COCO dataset
       │
  person_count = 3
       │
  [Map to graph via camera_node_map]
       │
  Update edge weights:
    weight = distance × (1 + count / capacity)
       │
  Re-run Dijkstra → new optimal path that avoids the crowded area
```

### Crowd-aware routing

If Room 3 is crowded (detected by CAM_02), its edges get a higher weight.
Dijkstra then automatically finds an alternate route bypassing that room.

### Simulation mode (for testing)

Since we don't have real cameras yet:
```python
counts = simulate_crowd_counts(camera_node_map, max_per_cam=8, seed=42)
# Returns: {'CAM_01': 1, 'CAM_02': 0, 'CAM_03': 4, 'CAM_04': 3}
```

---

## Complete File Tree

```
indoornav/
│
├── data/raw/
│   └── Grethes-hus-bok-2.ifc          ← input IFC file
│
├── src/                                ← all Python source code
│   ├── main.py                         ← CLI: run the full pipeline
│   ├── load_ifc.py                     ← Stage 1: open + validate IFC
│   ├── extract_geometry.py             ← Stage 2-3: triangulate geometry
│   ├── export_model.py                 ← Stage 4: save .obj .glb .json
│   ├── visualize.py                    ← Stage 5: render screenshot
│   ├── build_graph.py                  ← Phase 2: IFC → nav graph
│   ├── navigate.py                     ← Phase 2: Dijkstra pathfinding
│   ├── cctv_integration.py             ← Phase 2: camera → graph mapping
│   └── crowd_detection.py             ← Phase 2: YOLOv8 person counting
│
├── dashboard/
│   └── index.html                      ← browser 3D viewer (no install needed)
│
├── outputs/                            ← generated by running the pipeline
│   ├── model.obj                       ← 3D mesh, Y-up, IFC colors
│   ├── model.glb                       ← binary glTF for web viewers
│   ├── elements.json                   ← GUID index of all elements
│   ├── render.png                      ← color-coded screenshot
│   ├── nav_graph.json                  ← navigation graph
│   ├── nav_graph.gexf                  ← Gephi graph format
│   ├── cameras.json                    ← CCTV camera positions
│   └── route_result.json              ← last computed navigation route
│
├── docs/
│   ├── architecture.md                 ← system design overview
│   ├── pipeline.md                     ← end-to-end walkthrough
│   ├── phase2_navigation.md            ← Phase 2 design doc
│   └── modules/
│       ├── load_ifc.md
│       ├── extract_geometry.md
│       ├── export_model.md
│       ├── visualize.md
│       └── dashboard.md
│
└── requirements.txt
```

---

## How to Run Everything

### Step 1 — Run the 3D pipeline
```powershell
python src/main.py --input "data/raw/Grethes-hus-bok-2.ifc" --output-dir outputs --no-display
```

### Step 2 — View in browser
```
Open:  dashboard/index.html
Drag:  outputs/model.obj  onto the viewport
```

### Step 3 — Build the navigation graph
```powershell
python -c "
import ifcopenshell, sys; sys.path.insert(0,'src')
from build_graph import build_graph_from_ifc
ifc = ifcopenshell.open('data/raw/Grethes-hus-bok-2.ifc')
build_graph_from_ifc(ifc, 'outputs')
"
```

### Step 4 — Find a route (simulation)
```powershell
python scratch/test_graph.py
```

---

## What's Next (Phase 3 ideas)

| Feature | Description |
|---|---|
| **Path overlay in dashboard** | Highlight the route on the 3D model in the browser |
| **Real CCTV feed** | Connect to an actual RTSP stream |
| **Floor plan 2D view** | Top-down 2D map with path drawn on it |
| **Seismic risk integration** | Weight edges by structural risk during earthquakes |
| **Multi-building routing** | Connect multiple IFC files |
| **API server** | REST API so a mobile app can request routes |
