"""
navigate.py — Multi-floor indoor routing engine (A* and Dijkstra).

Operates on the physically-constrained navigation graph produced by build_graph.py.
Respects walls, door portals, stairs/elevators, accessibility constraints,
and real-time crowd densities from CCTV feeds.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

WALK_SPEED_MS = 1.2   # m/s average walking speed
DEFAULT_CAPACITY = 10 # default crowd capacity before edge penalty


# ─────────────────────────────────────────────────────────────────────────────
# Result Containers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FloorTransition:
    """Represents a change of floors via stair or elevator."""
    from_floor: int
    to_floor:   int
    type:       str    # "stair" | "elevator"
    via_node:   str    # Node ID of the transition element
    distance_m: float = 0.0

    def to_dict(self) -> dict:
        return {
            "from": self.from_floor,
            "to": self.to_floor,
            "type": self.type,
            "via_node": self.via_node,
            "distance_m": round(self.distance_m, 2),
        }


@dataclass
class RouteStep:
    """One step in a navigation route."""
    node_guid:    str
    node_name:    str
    ifc_type:     str
    storey:       str
    floor:        int
    centroid:     List[float]
    instruction:  str           # human-readable direction text
    via_type:     str = ""      # "door", "stair", "elevator", "corridor", "walk"
    distance_m:   float = 0.0


@dataclass
class RouteResult:
    """Complete navigation result from source to destination."""
    source_guid:       str
    target_guid:       str
    source_name:       str
    target_name:       str
    found:             bool
    success:           bool  = False     # Alias for found
    distance_m:        float = 0.0       # Alias for total_distance_m
    total_distance_m:  float = 0.0
    estimated_time_s:  float = 0.0
    crowd_avoided:     bool  = False
    storey_changes:    int   = 0
    route:             List[str] = field(default_factory=list) # Ordered list of node IDs
    floor_transitions: List[Dict[str, Any]] = field(default_factory=list)
    steps:             List[RouteStep] = field(default_factory=list)
    error:             str   = ""

    def __post_init__(self):
        self.success = self.found
        if self.distance_m == 0.0 and self.total_distance_m > 0.0:
            self.distance_m = self.total_distance_m
        elif self.total_distance_m == 0.0 and self.distance_m > 0.0:
            self.total_distance_m = self.distance_m

    def print_summary(self) -> None:
        sep = "-" * 55
        print(sep)
        print(f"  ROUTE: {self.source_name}  ->  {self.target_name}")
        print(sep)
        if not self.found:
            print(f"  ERROR: {self.error}")
        else:
            print(f"  Status         : SUCCESS")
            print(f"  Total distance : {self.total_distance_m:.1f} m")
            print(f"  Estimated time : {self.estimated_time_s:.0f} s ({self.estimated_time_s/60:.1f} min)")
            print(f"  Floor changes  : {len(self.floor_transitions)}")
            print(f"  Crowd avoided  : {'Yes' if self.crowd_avoided else 'No'}")
            print(f"  Nodes in route : {len(self.route)}")
            print(sep)
            for i, step in enumerate(self.steps):
                prefix = "START" if i == 0 else ("DEST " if i == len(self.steps) - 1 else f"  {i:02d} ")
                via = f"  (via {step.via_type})" if step.via_type else ""
                print(f"  {prefix} [Floor {step.floor}] {step.node_name}{via}")
            if self.floor_transitions:
                print("\n  Floor Transitions:")
                for ft in self.floor_transitions:
                    print(f"    - Floor {ft['from']} -> Floor {ft['to']} via {ft['type']} ({ft['via_node']})")
        print(sep)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.source_guid
        d["destination"] = self.target_guid
        return d

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return path


# ─────────────────────────────────────────────────────────────────────────────
# Pathfinding Heuristic for A*
# ─────────────────────────────────────────────────────────────────────────────

def _make_heuristic(G: nx.Graph, target: str):
    """
    Admissible 3D Euclidean distance heuristic with floor transition penalty.
    """
    t_data = G.nodes[target]
    tx = float(t_data.get("x", 0.0))
    ty = float(t_data.get("y", 0.0))
    tz = float(t_data.get("z", t_data.get("elevation", 0.0)))
    t_floor = int(t_data.get("floor", 1))

    def heuristic(u: str, v: str = target) -> float:
        u_data = G.nodes[u]
        ux = float(u_data.get("x", 0.0))
        uy = float(u_data.get("y", 0.0))
        uz = float(u_data.get("z", u_data.get("elevation", 0.0)))
        u_floor = int(u_data.get("floor", 1))

        # 3D Euclidean distance
        euclid = math.sqrt((ux - tx)**2 + (uy - ty)**2 + (uz - tz)**2)
        # Floor change penalty ensures A* prioritizes direct stair routes
        floor_penalty = abs(u_floor - t_floor) * 3.0
        return euclid + floor_penalty

    return heuristic


# ─────────────────────────────────────────────────────────────────────────────
# Turn-by-Turn Instruction Generator
# ─────────────────────────────────────────────────────────────────────────────

def _make_instruction(
    prev_step: Optional[RouteStep],
    cur_data: Dict[str, Any],
    edge_data: Optional[Dict[str, Any]],
    is_last: bool,
) -> str:
    name = cur_data.get("name", "area")
    ntype = cur_data.get("type", "")
    etype = edge_data.get("type", "walk") if edge_data else "walk"

    if is_last:
        return f"Arrive at destination: {name}"

    if etype in ("stair", "vertical"):
        direction = "up" if cur_data.get("z", 0) > (prev_step.centroid[2] if prev_step else 0) else "down"
        return f"Take stairs {direction} to Floor {cur_data.get('floor', 1)} ({cur_data.get('storey', '')})"

    if etype == "elevator":
        return f"Take elevator to Floor {cur_data.get('floor', 1)}"

    if etype in ("door", "gate") or ntype in ("door", "gate"):
        return f"Pass through {name}"

    dist_m = edge_data.get("distance_m", 0.0) if edge_data else 0.0
    return f"Walk {dist_m:.1f} m through {name}"


# ─────────────────────────────────────────────────────────────────────────────
# Core Routing Engine
# ─────────────────────────────────────────────────────────────────────────────

def find_route(
    G: nx.Graph,
    source_guid: str,
    target_guid: str,
    *,
    avoid_crowded: bool = True,
    max_crowd_weight: float = 4.0,
    accessible_only: bool = False,
    algorithm: str = "astar",
) -> RouteResult:
    """
    Find the shortest, collision-safe route between two navigation nodes.

    Parameters
    ----------
    G : NetworkX graph built by build_graph.py
    source_guid : ID of starting node
    target_guid : ID of destination node
    avoid_crowded : If True, uses crowd-adjusted weights; else pure distance
    max_crowd_weight : Edges with crowd_weight exceeding this are filtered out
    accessible_only : If True, excludes stairs (wheelchair accessible)
    algorithm : "astar" (default) or "dijkstra"

    Returns
    -------
    RouteResult populated with ordered route, transitions, and metrics.
    """
    source_data = G.nodes.get(source_guid, {})
    target_data = G.nodes.get(target_guid, {})

    result = RouteResult(
        source_guid=source_guid,
        target_guid=target_guid,
        source_name=source_data.get("name", source_guid),
        target_name=target_data.get("name", target_guid),
        found=False,
    )

    if source_guid not in G:
        result.error = f"Source node '{source_guid}' does not exist in graph."
        return result
    if target_guid not in G:
        result.error = f"Destination node '{target_guid}' does not exist in graph."
        return result
    if source_guid == target_guid:
        result.found = True
        result.success = True
        result.route = [source_guid]
        result.steps = [RouteStep(
            node_guid=source_guid,
            node_name=result.source_name,
            ifc_type=source_data.get("type", ""),
            storey=source_data.get("storey", ""),
            floor=int(source_data.get("floor", 1)),
            centroid=[source_data.get("x", 0), source_data.get("y", 0), source_data.get("z", 0)],
            instruction="You are already at your destination.",
        )]
        return result

    # Filter graph view based on accessibility and crowd constraints
    def edge_allowed(u, v):
        ed = G.edges[u, v]
        if accessible_only and not ed.get("accessible", True):
            return False
        if avoid_crowded and ed.get("crowd_weight", 1.0) > max_crowd_weight:
            return False
        return True

    try:
        active_graph = nx.subgraph_view(G, filter_edge=edge_allowed)
        if not nx.has_path(active_graph, source_guid, target_guid):
            # Fall back to base graph if crowd filter made it unreachable
            if accessible_only:
                base_allowed = lambda u, v: G.edges[u, v].get("accessible", True)
                active_graph = nx.subgraph_view(G, filter_edge=base_allowed)
            else:
                active_graph = G
            result.crowd_avoided = False
        else:
            result.crowd_avoided = avoid_crowded
    except Exception:
        active_graph = G
        result.crowd_avoided = False

    if not nx.has_path(active_graph, source_guid, target_guid):
        result.error = f"No physical path exists between '{result.source_name}' and '{result.target_name}'."
        return result

    # Execute pathfinding
    weight_field = "weight" if avoid_crowded else "distance_m"

    try:
        if algorithm.lower() == "astar":
            heuristic_fn = _make_heuristic(G, target_guid)
            node_path = nx.astar_path(active_graph, source_guid, target_guid, heuristic=heuristic_fn, weight=weight_field)
        else:
            node_path = nx.dijkstra_path(active_graph, source_guid, target_guid, weight=weight_field)
    except Exception as exc:
        result.error = f"Pathfinding error: {exc}"
        return result

    result.found = True
    result.success = True
    result.route = node_path

    # Construct steps, measure metrics and detect floor transitions
    total_dist = 0.0
    transitions: List[Dict[str, Any]] = []
    steps: List[RouteStep] = []

    for i, nid in enumerate(node_path):
        nd = G.nodes[nid]
        edge_data = None
        dist_step = 0.0
        via = ""

        if i < len(node_path) - 1:
            nxt = node_path[i + 1]
            edge_data = G.edges[nid, nxt]
            dist_step = float(edge_data.get("distance_m", 0.0))
            via = str(edge_data.get("type", edge_data.get("edge_type", "")))
            total_dist += dist_step

            # Check floor transition
            f_cur = int(nd.get("floor", 1))
            f_nxt = int(G.nodes[nxt].get("floor", 1))
            if f_cur != f_nxt:
                tr_type = "stair" if via in ("stair", "vertical") else "elevator"
                transitions.append(FloorTransition(
                    from_floor=f_cur,
                    to_floor=f_nxt,
                    type=tr_type,
                    via_node=nxt,
                    distance_m=dist_step,
                ).to_dict())

        prev_step = steps[-1] if steps else None
        instruction = _make_instruction(prev_step, nd, edge_data, is_last=(i == len(node_path) - 1))

        steps.append(RouteStep(
            node_guid=nid,
            node_name=nd.get("name", nid),
            ifc_type=nd.get("type", ""),
            storey=nd.get("storey", ""),
            floor=int(nd.get("floor", 1)),
            centroid=[float(nd.get("x", 0.0)), float(nd.get("y", 0.0)), float(nd.get("z", 0.0))],
            instruction=instruction,
            via_type=via,
            distance_m=round(dist_step, 2),
        ))

    result.steps = steps
    result.total_distance_m = round(total_dist, 2)
    result.distance_m = result.total_distance_m
    result.estimated_time_s = round(total_dist / WALK_SPEED_MS, 1)
    result.floor_transitions = transitions
    result.storey_changes = len(transitions)

    return result


def find_route_by_name(
    G: nx.Graph,
    nodes: Dict[str, Any],
    source_name: str,
    target_name: str,
    **kwargs,
) -> RouteResult:
    """Find route using human-readable space/node names."""
    src_id = None
    dst_id = None

    for nid, d in G.nodes(data=True):
        nname = d.get("name", "").lower()
        if source_name.lower() in nname and src_id is None:
            src_id = nid
        if target_name.lower() in nname and dst_id is None:
            dst_id = nid

    if not src_id:
        res = RouteResult(source_guid="", target_guid="", source_name=source_name, target_name=target_name, found=False)
        res.error = f"Source space '{source_name}' not found."
        return res

    if not dst_id:
        res = RouteResult(source_guid=src_id, target_guid="", source_name=source_name, target_name=target_name, found=False)
        res.error = f"Destination space '{target_name}' not found."
        return res

    return find_route(G, src_id, dst_id, **kwargs)


def update_crowd_weights(
    G: nx.Graph,
    camera_counts: Dict[str, int],
    camera_node_map: Dict[str, List[str]],
) -> None:
    """
    Propagate CCTV camera detection counts to graph nodes and incident edges.
    Increases edge cost dynamically:
      weight = distance_m * (1.0 + crowd / capacity)
    """
    for cam_id, count in camera_counts.items():
        covered_nodes = camera_node_map.get(cam_id, [])
        for nid in covered_nodes:
            if nid not in G:
                continue
            for neighbor in G.neighbors(nid):
                ed = G.edges[nid, neighbor]
                cap = ed.get("capacity", DEFAULT_CAPACITY)
                dist = ed.get("distance_m", 1.0)
                ed["crowd_count"] = count
                ed["crowd_weight"] = 1.0 + (count / max(cap, 1))
                ed["weight"] = dist * ed["crowd_weight"]
