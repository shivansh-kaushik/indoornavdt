# Phase 2 — Physically-Constrained Multi-Floor Indoor Navigation Graph

> **Built on top of**: Phase 1 (IFC → 3D Model)  
> **Status**: Completed & Validated

---

## Core Invariant

> **A user may move only through explicitly defined navigation nodes and valid connections. Walls are hard barriers. Doors/gates are horizontal passage points. Stairs/elevators are vertical passage points between floors. No shortcuts or wall-crossings are permitted.**

---

## Problem Statement

GPS does not work indoors. To navigate reliably inside a building we require:
1. A **physically constrained topological graph** representing walkable floor space, doors, and stairs/elevators.
2. An **architectural collision engine** preventing candidate paths or avatars from penetrating walls.
3. An **A\* / Dijkstra pathfinding algorithm** calculating shortest, multi-floor, crowd-aware routes.
4. **Real-time crowd data** from CCTV cameras to dynamically re-weight routes.
5. An **interactive 3D dashboard** providing 3D route rendering, turn-by-turn guidance, collision-constrained walk mode, and a graph authoring editor.

---

## System Architecture

```
src/
├── navigation/
│   ├── collision.py        # Wall geometry extraction & 2D/3D collision detector
│   └── route_validator.py  # Graph integrity, wall crossing & connectivity validator
├── build_graph.py          # IFC -> Physically-constrained multi-floor NetworkX graph
├── navigate.py             # Multi-floor A* & Dijkstra routing with crowd penalties
├── cctv_integration.py     # Map CCTV cameras onto graph nodes/edges
└── crowd_detection.py      # YOLOv8 / OpenCV person counting per camera
```

---

## Data Schemas

### Navigation Node
```json
{
  "id": "node_0BTBFw_01",
  "type": "corridor",
  "floor": 1,
  "storey_id": "Level 1",
  "space_id": "0BTBFw9p907x1G5lCpt19a",
  "name": "Corridor A (W1)",
  "x": 6.42,
  "y": -8.15,
  "z": 0.10,
  "elevation": 0.0,
  "clearance_m": 0.30
}
```

### Navigation Edge
```json
{
  "from": "node_0BTBFw_01",
  "to": "door_1hOSvn6d",
  "type": "door",
  "distance_m": 2.4,
  "floor_from": 1,
  "floor_to": 1,
  "accessible": true,
  "crowd_count": 0,
  "crowd_weight": 1.0,
  "weight": 2.4
}
```

### Vertical Edge (Stairs / Elevators)
```json
{
  "from": "stair_bot_3AHN05",
  "to": "stair_top_3AHN05",
  "type": "stair",
  "floor_from": 1,
  "floor_to": 2,
  "distance_m": 4.8,
  "accessible": false
}
```

---

## Physical Constraint Enforcement

### 1. Wall Barrier Enforcement (`collision.py`)
- Wall geometries (`IfcWall`, `IfcWallStandardCase`) are extracted as exact 2D footprint polygons per storey.
- Door portals are subtracted to yield solid wall geometry.
- For every candidate edge:
  $$\text{LineSegment}(P_1, P_2) \cap \text{SolidWall} \neq \emptyset \implies \text{REJECT}$$
- Segment intersections outside authorized door portals are rejected at graph construction time.

### 2. Intermediate Walking Nodes
- Corridors and large spaces are sampled at 1–2m intervals using a 2D grid within the space boundary.
- Wall clearance ($0.30\text{m}$) ensures nodes are placed safely away from walls and obstacles.

### 3. Multi-Floor Circulation
- Floors change **only** through stairs or elevators.
- Stair flights produce linked bottom and top landing nodes on their respective storeys.

---

## Outputs

All artifacts land in `outputs/`:

| File | Description |
|---|---|
| `nav_graph.json` | Complete graph serialization (metadata, nodes, edges) |
| `nav_graph.gexf` | Gephi-compatible XML graph format |
| `navigation_nodes.json` | Standalone array of all navigation nodes |
| `navigation_edges.json` | Standalone array of all valid connections |
| `navigation_validation.json` | Detailed validation and diagnostic report |
| `navigation_routes.json` | Exported calculated routes and turn instructions |

---

## Verification & Automated Test Suite

Run the 8-test verification suite:
```powershell
python tests/test_navigation.py
```
Covers:
1. Room A $\to$ Room B through door $\to$ `PASS`
2. Room A $\to$ Room B separated by wall $\to$ `NO ROUTE`
3. Floor 1 $\to$ Floor 2 via stairs $\to$ `PASS`
4. Floor 1 $\to$ Floor 2 without vertical portal $\to$ `NO ROUTE`
5. Floor 1 $\to$ Floor 3 via elevator $\to$ `PASS`
6. Virtual movement into wall $\to$ `MOVEMENT BLOCKED`
7. Crowded corridor $\to$ Alternative route selected
8. Single corridor bottleneck $\to$ Same route with crowd cost
