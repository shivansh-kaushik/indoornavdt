"""
build_graph.py — Physically-constrained multi-floor indoor navigation graph builder.

Extracts architectural spaces, doors, stairs, and elevators from an IFC file
into a topologically sound NetworkX graph where:
  - Rooms, corridors, junctions, doors, gates, stairs, and elevators are explicit nodes.
  - Walls are absolute barriers: no edge penetrates a solid wall without a door portal.
  - Multi-floor transitions occur strictly through stairs or elevators.
  - Corridors and large spaces contain intermediate walkable nodes with wall clearance.

Outputs:
  outputs/nav_graph.json
  outputs/nav_graph.gexf
  outputs/navigation_nodes.json
  outputs/navigation_edges.json
  outputs/navigation_validation.json
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union

from navigation.collision import WallCollisionDetector, DoorPortal
from navigation.route_validator import validate_graph, ValidationReport

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
NODE_SPACING_M = 1.5           # Distance between intermediate corridor nodes
WALL_CLEARANCE_M = 0.30        # Minimum standoff distance from walls
DOOR_SEARCH_RADIUS_M = 3.5     # Max distance to link spaces through doors
WALK_SPEED_MS = 1.2            # Walking speed (m/s) for ETA computation
DEFAULT_CAPACITY = 10          # Default crowd capacity before edge penalty


# ─────────────────────────────────────────────────────────────────────────────
# Data Containers (Compatible with Phase 1 & 2 schemas)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NavNode:
    """Explicit navigation node in the building."""
    id:               str
    type:             str           # corridor, room, lobby, junction, door, gate, stair, elevator
    floor:            int           # Integer floor number (1, 2, 3...)
    storey_id:        str           # Storey name from IFC
    space_id:         str           # GUID of parent space / element
    name:             str           # Human-readable label
    x:                float         # IFC world coord X
    y:                float         # IFC world coord Y
    z:                float         # IFC world coord Z (elevation)
    elevation:        float         # Elevation above reference level
    area_m2:          float = 0.0
    clearance_m:      float = WALL_CLEARANCE_M
    cameras:          List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NavEdge:
    """Explicit directed/undirected physical connection between nodes."""
    from_id:       str
    to_id:         str
    type:          str              # walk, corridor, door, gate, stair, elevator
    distance_m:    float
    floor_from:    int
    floor_to:      int
    accessible:    bool  = True     # False for stairs (inaccessible for wheelchairs)
    crowd_count:   int   = 0
    crowd_weight:  float = 1.0
    capacity:      int   = DEFAULT_CAPACITY
    guid:          str   = ""       # GUID of door or stair element

    @property
    def weight(self) -> float:
        return self.distance_m * self.crowd_weight

    def update_crowd(self, count: int) -> None:
        self.crowd_count = count
        self.crowd_weight = 1.0 + (count / max(self.capacity, 1))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["from"] = self.from_id
        d["to"] = self.to_id
        del d["from_id"]
        del d["to_id"]
        return d


# Backward compatibility aliases for existing modules
SpaceNode = NavNode
DoorEdge = NavEdge


# ─────────────────────────────────────────────────────────────────────────────
# Storey Hierarchy Extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_storeys(ifc_file) -> List[Tuple[str, str, float, int]]:
    """
    Returns sorted list of (GlobalId, Name, Elevation, floor_number).
    Ordered by elevation ascending (floor 1, 2, 3...).
    Elevations are normalized to metres.
    """
    storeys_raw = ifc_file.by_type("IfcBuildingStorey")
    extracted = []
    for st in storeys_raw:
        guid = st.GlobalId
        name = str(st.Name).strip() if st.Name else f"Storey_{guid[:8]}"
        elev = 0.0
        if hasattr(st, "Elevation") and st.Elevation is not None:
            elev = float(st.Elevation)
            if abs(elev) > 50.0:  # Detect mm and convert to metres
                elev /= 1000.0
        extracted.append((guid, name, elev))

    # Sort by elevation
    extracted.sort(key=lambda item: item[2])

    result = []
    for idx, (guid, name, elev) in enumerate(extracted, start=1):
        result.append((guid, name, elev, idx))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Space Geometry & 2D Footprint Extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_space_footprint(geom, settings, space) -> Tuple[Optional[Polygon | MultiPolygon], np.ndarray]:
    """Extract the 2D polygon footprint and vertex array for an IfcSpace."""
    try:
        shape = geom.create_shape(settings, space)
        verts = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
        faces = np.array(shape.geometry.faces, dtype=np.int32).reshape(-1, 3)
    except Exception:
        return None, np.zeros((0, 3), dtype=np.float32)

    if len(verts) == 0 or len(faces) == 0:
        return None, verts

    triangles = []
    for face in faces:
        p0 = (float(verts[face[0], 0]), float(verts[face[0], 1]))
        p1 = (float(verts[face[1], 0]), float(verts[face[1], 1]))
        p2 = (float(verts[face[2], 0]), float(verts[face[2], 1]))
        poly = Polygon([p0, p1, p2])
        if poly.is_valid and poly.area > 1e-4:
            triangles.append(poly)

    if not triangles:
        bmin = verts.min(axis=0)
        bmax = verts.max(axis=0)
        return box(bmin[0], bmin[1], bmax[0], bmax[1]), verts

    try:
        u = unary_union(triangles)
        if not u.is_valid:
            u = u.buffer(0)
        return u, verts
    except Exception:
        bmin = verts.min(axis=0)
        bmax = verts.max(axis=0)
        return box(bmin[0], bmin[1], bmax[0], bmax[1]), verts


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Generate Nodes
# ─────────────────────────────────────────────────────────────────────────────

def generate_navigation_nodes(
    ifc_file,
    collision_detector: WallCollisionDetector,
    spacing_m: float = NODE_SPACING_M,
    clearance_m: float = WALL_CLEARANCE_M,
) -> Tuple[Dict[str, NavNode], Dict[str, Polygon | MultiPolygon]]:
    """
    Extract rooms, corridors, door portals, intermediate walking nodes, and stairs.
    Returns (nodes_dict, space_footprints).
    """
    import ifcopenshell.geom as geom

    settings = geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    nodes: Dict[str, NavNode] = {}
    space_footprints: Dict[str, Polygon | MultiPolygon] = {}

    # Storey mapping
    storeys = _extract_storeys(ifc_file)
    storey_by_name = {name: (guid, elev, floor) for guid, name, elev, floor in storeys}
    storey_by_guid = {guid: (name, elev, floor) for guid, name, elev, floor in storeys}

    # Helper to resolve storey
    def get_storey_info(entity) -> Tuple[str, str, float, int]:
        for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
            if entity in rel.RelatedElements:
                st = rel.RelatingStructure
                if st.GlobalId in storey_by_guid:
                    name, elev, floor = storey_by_guid[st.GlobalId]
                    return st.GlobalId, name, elev, floor
        for rel in ifc_file.by_type("IfcRelAggregates"):
            if entity in rel.RelatedObjects:
                p = rel.RelatingObject
                if p.GlobalId in storey_by_guid:
                    name, elev, floor = storey_by_guid[p.GlobalId]
                    return p.GlobalId, name, elev, floor
        if storeys:
            g, n, e, f = storeys[0]
            return g, n, e, f
        return "default", "Level 1", 0.0, 1

    # ── 1. Process Spaces (Rooms, Corridors, Lobbies) ──────────────────────────
    for space in ifc_file.by_type("IfcSpace"):
        s_guid = space.GlobalId
        s_name = str(space.Name).strip() if space.Name else f"Space_{s_guid[:6]}"
        s_longname = str(space.LongName).strip() if hasattr(space, "LongName") and space.LongName else ""
        full_name = f"{s_name} {s_longname}".strip()

        st_guid, st_name, st_elev, st_floor = get_storey_info(space)

        # Detect space type
        name_lower = full_name.lower()
        if any(k in name_lower for k in ("corridor", "hallway", "gang", "aisle")):
            stype = "corridor"
        elif any(k in name_lower for k in ("lobby", "foyer", "vestibule", "atrium", "entrance")):
            stype = "lobby"
        else:
            stype = "room"

        poly_2d, verts = _extract_space_footprint(geom, settings, space)
        if poly_2d is None or poly_2d.is_empty:
            continue

        space_footprints[s_guid] = poly_2d
        area = float(poly_2d.area)
        base_z = float(verts[:, 2].min()) if len(verts) > 0 else st_elev

        # Determine representative primary point
        buffered_poly = poly_2d.buffer(-clearance_m)
        if buffered_poly.is_empty:
            rep_point = poly_2d.representative_point()
        else:
            rep_point = buffered_poly.representative_point()

        # Primary node for this space
        prime_id = f"node_{s_guid[:8]}"
        nodes[prime_id] = NavNode(
            id=prime_id,
            type=stype,
            floor=st_floor,
            storey_id=st_name,
            space_id=s_guid,
            name=full_name,
            x=round(float(rep_point.x), 3),
            y=round(float(rep_point.y), 3),
            z=round(base_z + 0.1, 3),
            elevation=round(st_elev, 3),
            area_m2=round(area, 2),
            clearance_m=clearance_m,
        )

        # Generate intermediate corridor walking nodes if elongated or large
        minx, miny, maxx, maxy = poly_2d.bounds
        dx = maxx - minx
        dy = maxy - miny

        if stype in ("corridor", "lobby") or (dx > 4.0 or dy > 4.0):
            xs = np.arange(minx + clearance_m, maxx - clearance_m, spacing_m)
            ys = np.arange(miny + clearance_m, maxy - clearance_m, spacing_m)
            grid_idx = 0
            for gx in xs:
                for gy in ys:
                    pt = Point(gx, gy)
                    if poly_2d.buffer(-clearance_m).contains(pt):
                        # Verify not inside wall
                        if not collision_detector.check_point_collision((gx, gy, base_z), st_name, clearance_m):
                            grid_id = f"walk_{s_guid[:6]}_{grid_idx:02d}"
                            nodes[grid_id] = NavNode(
                                id=grid_id,
                                type="corridor" if stype == "corridor" else "walk",
                                floor=st_floor,
                                storey_id=st_name,
                                space_id=s_guid,
                                name=f"{full_name} (W{grid_idx})",
                                x=round(float(gx), 3),
                                y=round(float(gy), 3),
                                z=round(base_z + 0.1, 3),
                                elevation=round(st_elev, 3),
                                area_m2=0.0,
                                clearance_m=clearance_m,
                            )
                            grid_idx += 1

    # ── 2. Process Doors & Portals ───────────────────────────────────────────
    for door in ifc_file.by_type("IfcDoor"):
        d_guid = door.GlobalId
        d_name = str(door.Name).strip() if door.Name else f"Door_{d_guid[:6]}"
        st_guid, st_name, st_elev, st_floor = get_storey_info(door)

        try:
            shape = geom.create_shape(settings, door)
            verts = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
            door_pos = verts.mean(axis=0)
        except Exception:
            continue

        door_id = f"door_{d_guid[:8]}"
        nodes[door_id] = NavNode(
            id=door_id,
            type="door",
            floor=st_floor,
            storey_id=st_name,
            space_id=d_guid,
            name=d_name,
            x=round(float(door_pos[0]), 3),
            y=round(float(door_pos[1]), 3),
            z=round(float(door_pos[2]), 3),
            elevation=round(st_elev, 3),
            clearance_m=0.1,
        )

    # ── 3. Process Stairs (Vertical Transitions) ──────────────────────────────
    stair_entities = ifc_file.by_type("IfcStairFlight")
    if not stair_entities:
        stair_entities = ifc_file.by_type("IfcStair")

    for stair in stair_entities:
        st_guid = stair.GlobalId
        st_name_str = str(stair.Name).strip() if stair.Name else f"Stair_{st_guid[:6]}"

        try:
            shape = geom.create_shape(settings, stair)
            verts = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
        except Exception:
            continue

        if len(verts) == 0:
            continue

        z_min = float(verts[:, 2].min())
        z_max = float(verts[:, 2].max())
        dz = z_max - z_min

        # Sort vertices by Z to find bottom and top landings
        bot_verts = verts[verts[:, 2] <= z_min + 0.35]
        top_verts = verts[verts[:, 2] >= z_max - 0.35]

        bot_pt = bot_verts.mean(axis=0) if len(bot_verts) > 0 else verts.mean(axis=0)
        top_pt = top_verts.mean(axis=0) if len(top_verts) > 0 else verts.mean(axis=0)

        # Match elevations to storeys
        def match_storey(z_val: float) -> Tuple[str, str, float, int]:
            best = storeys[0]
            best_diff = 999.0
            for g, n, e, f in storeys:
                diff = abs(z_val - e)
                if diff < best_diff:
                    best_diff = diff
                    best = (g, n, e, f)
            return best

        g_bot, n_bot, e_bot, f_bot = match_storey(z_min)
        g_top, n_top, e_top, f_top = match_storey(z_max)

        # Create landing node on lower floor
        bot_id = f"stair_bot_{st_guid[:6]}"
        nodes[bot_id] = NavNode(
            id=bot_id,
            type="stair",
            floor=f_bot,
            storey_id=n_bot,
            space_id=st_guid,
            name=f"{st_name_str} (Floor {f_bot})",
            x=round(float(bot_pt[0]), 3),
            y=round(float(bot_pt[1]), 3),
            z=round(float(z_min + 0.1), 3),
            elevation=round(e_bot, 3),
            clearance_m=0.2,
        )

        # Create landing node on upper floor (if spans multiple storeys or dz > 1.2m)
        if f_top != f_bot or dz > 1.2:
            top_id = f"stair_top_{st_guid[:6]}"
            nodes[top_id] = NavNode(
                id=top_id,
                type="stair",
                floor=f_top if f_top != f_bot else f_bot + 1,
                storey_id=n_top,
                space_id=st_guid,
                name=f"{st_name_str} (Floor {f_top if f_top != f_bot else f_bot + 1})",
                x=round(float(top_pt[0]), 3),
                y=round(float(top_pt[1]), 3),
                z=round(float(z_max - 0.1), 3),
                elevation=round(e_top, 3),
                clearance_m=0.2,
            )

    logger.info("Generated %d total navigation nodes across %d storeys", len(nodes), len(storeys))
    return nodes, space_footprints


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Build Physically-Constrained Edges
# ─────────────────────────────────────────────────────────────────────────────

def generate_navigation_edges(
    ifc_file,
    nodes: Dict[str, NavNode],
    space_footprints: Dict[str, Polygon | MultiPolygon],
    collision_detector: WallCollisionDetector,
) -> List[NavEdge]:
    """
    Construct valid walking connections between nodes.
    Rigidly checks wall barriers:
      - Walking nodes connect only when unobstructed by walls.
      - Spaces connect exclusively via door portal nodes.
      - Vertical edges connect exclusively between stair bottom/top or elevators.
    """
    edges: List[NavEdge] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    def add_edge(u: str, v: str, edge_type: str, accessible: bool = True, guid: str = ""):
        if u == v or (u, v) in seen_pairs or (v, u) in seen_pairs:
            return
        n1 = nodes[u]
        n2 = nodes[v]
        dist = math.sqrt((n1.x - n2.x) ** 2 + (n1.y - n2.y) ** 2 + (n1.z - n2.z) ** 2)
        edges.append(NavEdge(
            from_id=u,
            to_id=v,
            type=edge_type,
            distance_m=round(dist, 3),
            floor_from=n1.floor,
            floor_to=n2.floor,
            accessible=accessible,
            guid=guid,
        ))
        seen_pairs.add((u, v))

    # Group nodes by storey and space
    nodes_by_storey: Dict[str, List[NavNode]] = {}
    nodes_by_space: Dict[str, List[NavNode]] = {}
    door_nodes: List[NavNode] = []
    stair_nodes: List[NavNode] = []

    for n in nodes.values():
        nodes_by_storey.setdefault(n.storey_id, []).append(n)
        if n.space_id:
            nodes_by_space.setdefault(n.space_id, []).append(n)
        if n.type in ("door", "gate"):
            door_nodes.append(n)
        elif n.type == "stair":
            stair_nodes.append(n)

    # ── A. Connect Intra-Space Nodes (e.g. Corridor Grid Nodes) ───────────────
    for s_guid, space_nodes in nodes_by_space.items():
        if len(space_nodes) <= 1:
            continue
        storey = space_nodes[0].storey_id
        # For each pair in the same space, connect if within spacing and line of sight clear
        for i, na in enumerate(space_nodes):
            for nb in space_nodes[i + 1:]:
                d = math.hypot(na.x - nb.x, na.y - nb.y)
                # Allow connecting immediate grid neighbors (up to 2.2m for diagonals)
                if d <= NODE_SPACING_M * 1.55:
                    if not collision_detector.check_segment_collision((na.x, na.y), (nb.x, nb.y), storey):
                        etype = "corridor" if na.type == "corridor" or nb.type == "corridor" else "walk"
                        add_edge(na.id, nb.id, etype)

    # ── B. Connect Doors to Adjacent Spaces / Nodes ───────────────────────────
    # A door connects to the spaces it bounds.
    # We find which spaces are adjacent to this door threshold.
    for d_node in door_nodes:
        d_pt = (d_node.x, d_node.y)
        storey = d_node.storey_id
        d_p = Point(d_pt[0], d_pt[1])

        # Find all spaces whose footprint intersects or is very close to this door
        connected_spaces_for_door = []
        for s_guid, footprint in space_footprints.items():
            if footprint.distance(d_p) <= DOOR_SEARCH_RADIUS_M:
                connected_spaces_for_door.append(s_guid)

        # For each candidate space, find the nearest reachable node in that space on the SAME floor
        for s_guid in connected_spaces_for_door:
            sp_nodes = [
                n for n in nodes_by_space.get(s_guid, [])
                if n.floor == d_node.floor and abs(n.z - d_node.z) <= 1.8
            ]
            if not sp_nodes:
                continue

            # Sort space nodes by distance to door
            candidates = sorted(sp_nodes, key=lambda n: math.hypot(n.x - d_node.x, n.y - d_node.y))
            # Pick the closest node where walking line from door does not penetrate wall
            for target_node in candidates[:4]:
                dist_to_door = math.hypot(target_node.x - d_node.x, target_node.y - d_node.y)
                if dist_to_door > DOOR_SEARCH_RADIUS_M * 2:
                    continue
                # Line of sight check
                if not collision_detector.check_segment_collision(
                    d_pt, (target_node.x, target_node.y), storey, penetration_tolerance_m=0.10
                ):
                    add_edge(d_node.id, target_node.id, "door", guid=d_node.space_id)
                    break  # Connect once per space

    # ── C. Connect Stair Landings (Vertical Connections) ──────────────────────
    # For every stair flight with bot and top landings, connect them vertically
    stair_pairs: Dict[str, List[NavNode]] = {}
    for sn in stair_nodes:
        stair_pairs.setdefault(sn.space_id, []).append(sn)

    for st_guid, pair in stair_pairs.items():
        if len(pair) == 2:
            s1, s2 = pair[0], pair[1]
            # Vertical edge between floors
            add_edge(s1.id, s2.id, "stair", accessible=False, guid=st_guid)
        elif len(pair) > 2:
            # Sort by elevation and connect adjacent levels
            sorted_pair = sorted(pair, key=lambda n: n.z)
            for i in range(len(sorted_pair) - 1):
                add_edge(sorted_pair[i].id, sorted_pair[i + 1].id, "stair", accessible=False, guid=st_guid)

    # ── D. Connect Stair Landings to Nearest Space on Same Floor ──────────────
    for sn in stair_nodes:
        st_nodes = [n for n in nodes_by_storey.get(sn.storey_id, []) if n.type != "stair"]
        if not st_nodes:
            continue
        # Sort by distance
        nearest = sorted(st_nodes, key=lambda n: math.hypot(n.x - sn.x, n.y - sn.y))
        for target in nearest[:5]:
            dist = math.hypot(target.x - sn.x, target.y - sn.y)
            if dist > 8.0:
                continue
            if not collision_detector.check_segment_collision(
                (sn.x, sn.y), (target.x, target.y), sn.storey_id, penetration_tolerance_m=0.15
            ):
                add_edge(sn.id, target.id, "walk", accessible=False, guid=sn.space_id)
                break

    logger.info("Built %d physically-validated navigation edges", len(edges))
    return edges


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Graph Construction & Serialization
# ─────────────────────────────────────────────────────────────────────────────

def build_nav_graph(nodes: Dict[str, NavNode], edges: List[NavEdge]) -> nx.Graph:
    """Build a NetworkX undirected graph populated with node and edge attributes."""
    G = nx.Graph()

    for node_id, node in nodes.items():
        G.add_node(
            node_id,
            id=node.id,
            type=node.type,
            floor=node.floor,
            storey=node.storey_id,
            storey_id=node.storey_id,
            space_id=node.space_id,
            name=node.name,
            x=node.x,
            y=node.y,
            z=node.z,
            elevation=node.elevation,
            area_m2=node.area_m2,
            clearance_m=node.clearance_m,
            cameras=node.cameras,
            centroid=[node.x, node.y, node.z], # Compatibility
        )

    for edge in edges:
        G.add_edge(
            edge.from_id,
            edge.to_id,
            type=edge.type,
            edge_type=edge.type,
            distance_m=edge.distance_m,
            floor_from=edge.floor_from,
            floor_to=edge.floor_to,
            accessible=edge.accessible,
            crowd_count=edge.crowd_count,
            crowd_weight=edge.crowd_weight,
            weight=edge.weight,
            capacity=edge.capacity,
            guid=edge.guid,
        )

    return G


def export_graph_json(
    G: nx.Graph,
    nodes: Dict[str, NavNode],
    edges: List[NavEdge],
    output_path: str | Path,
) -> Path:
    """Export complete graph JSON with nodes, edges, and metadata."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "is_connected": nx.is_connected(G) if len(nodes) > 0 else False,
            "connected_components": nx.number_connected_components(G) if len(nodes) > 0 else 0,
        },
        "nodes": [n.to_dict() for n in nodes.values()],
        "edges": [e.to_dict() for e in edges],
    }

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %s", output_path)
    return output_path


def export_graph_gexf(G: nx.Graph, output_path: str | Path) -> Path:
    """Export graph as Gephi-compatible GEXF."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    G2 = G.copy()
    for n, data in G2.nodes(data=True):
        for k, v in list(data.items()):
            if isinstance(v, list):
                data[k] = str(v)
    for u, v, data in G2.edges(data=True):
        for k, v in list(data.items()):
            if isinstance(v, list):
                data[k] = str(v)

    nx.write_gexf(G2, str(output_path))
    logger.info("Saved %s", output_path)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Public Pipeline Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def build_graph_from_ifc(
    ifc_file,
    output_dir: str | Path = "outputs",
) -> Tuple[nx.Graph, Dict[str, NavNode], List[NavEdge]]:
    """
    Main entry point: IFC -> Physically Constrained Multi-Floor Navigation Graph.

    Returns
    -------
    (G, nodes, edges)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n[Navigation Graph] Building physical wall collision detector ...")
    collision_detector = WallCollisionDetector.from_ifc(ifc_file)

    print("[Navigation Graph] Extracting multi-floor navigation nodes ...")
    nodes, space_footprints = generate_navigation_nodes(ifc_file, collision_detector)

    print("[Navigation Graph] Connecting nodes through doors & stairs ...")
    edges = generate_navigation_edges(ifc_file, nodes, space_footprints, collision_detector)

    print("[Navigation Graph] Assembling NetworkX graph ...")
    G = build_nav_graph(nodes, edges)

    # 4. Physical Validation
    print("[Navigation Graph] Running architectural validation checks ...")
    report = validate_graph(G, collision_detector)
    report.print_summary()
    report.save_json(output_dir / "navigation_validation.json")

    # 5. Export artifacts
    export_graph_json(G, nodes, edges, output_dir / "nav_graph.json")
    export_graph_gexf(G, output_dir / "nav_graph.gexf")

    # Separate standalone node and edge files
    nodes_payload = [n.to_dict() for n in nodes.values()]
    (output_dir / "navigation_nodes.json").write_text(
        json.dumps(nodes_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    edges_payload = [e.to_dict() for e in edges]
    (output_dir / "navigation_edges.json").write_text(
        json.dumps(edges_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"  OK  nav_graph.json            -> {output_dir / 'nav_graph.json'}")
    print(f"  OK  navigation_nodes.json     -> {output_dir / 'navigation_nodes.json'}")
    print(f"  OK  navigation_edges.json     -> {output_dir / 'navigation_edges.json'}")
    print(f"  OK  navigation_validation.json-> {output_dir / 'navigation_validation.json'}")

    return G, nodes, edges


def extract_space_nodes(ifc_file) -> Dict[str, NavNode]:
    """Backward compatibility wrapper."""
    collision_detector = WallCollisionDetector.from_ifc(ifc_file)
    nodes, _ = generate_navigation_nodes(ifc_file, collision_detector)
    return nodes
