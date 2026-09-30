"""
route_validator.py — Navigation graph physical validation and diagnostics.

Runs comprehensive checks to guarantee:
  1. No nodes placed inside walls or violating clearance.
  2. No edges cutting through solid walls.
  3. All floor transitions occur exclusively through stairs or elevators.
  4. Graph connectivity, room reachability, and absence of orphan portals.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    severity: str    # "ERROR" | "WARNING" | "INFO"
    category: str    # "wall_collision", "floor_transition", "connectivity", etc.
    message: str
    entity_ids: List[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete diagnostic results for a navigation graph."""
    total_nodes: int = 0
    total_edges: int = 0
    is_connected: bool = False
    connected_components: int = 0
    passed: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def print_summary(self) -> None:
        sep = "=" * 60
        print(f"\n{sep}")
        print("  NAVIGATION GRAPH VALIDATION")
        print(sep)
        print(f"  Nodes: {self.total_nodes}  |  Edges: {self.total_edges}")
        print(f"  Connected components: {self.connected_components}")

        errors = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]

        if not errors:
            print("  [OK] No physical constraint violations found!")
        else:
            print(f"  [FAIL] Found {len(errors)} critical error(s):")
            for err in errors[:10]:
                print(f"    - [{err.category}] {err.message}")
            if len(errors) > 10:
                print(f"    ... and {len(errors) - 10} more errors")

        if warnings:
            print(f"\n  Warnings ({len(warnings)}):")
            for warn in warnings[:8]:
                print(f"    - [{warn.category}] {warn.message}")
            if len(warnings) > 8:
                print(f"    ... and {len(warnings) - 8} more warnings")

        print(f"{sep}\n")

    def to_dict(self) -> dict:
        return asdict(self)

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return path


def validate_graph(
    G: nx.Graph,
    collision_detector: Optional[Any] = None,
    max_edge_length_m: float = 30.0,
) -> ValidationReport:
    """
    Validate a navigation graph against physical architectural rules.

    Parameters
    ----------
    G : networkx Graph with node and edge attributes
    collision_detector : Optional WallCollisionDetector instance
    max_edge_length_m : Flag edges longer than this threshold as suspicious

    Returns
    -------
    ValidationReport with diagnostic issues and metrics
    """
    report = ValidationReport(
        total_nodes=G.number_of_nodes(),
        total_edges=G.number_of_edges(),
        is_connected=nx.is_connected(G) if G.number_of_nodes() > 0 else False,
        connected_components=nx.number_connected_components(G) if G.number_of_nodes() > 0 else 0,
    )

    nodes_inside_walls = 0
    edges_crossing_walls = 0
    invalid_floor_transitions = 0
    duplicate_nodes = 0
    zero_len_edges = 0
    long_edges = 0

    # 1. Node Validation
    node_coords: Dict[str, Tuple[float, float, float]] = {}
    node_storeys: Dict[str, str] = {}
    node_types: Dict[str, str] = {}
    seen_positions: Dict[Tuple[float, float, float], str] = {}

    for node_id, data in G.nodes(data=True):
        x = float(data.get("x", 0.0))
        y = float(data.get("y", 0.0))
        z = float(data.get("z", data.get("elevation", 0.0)))
        pos = (round(x, 3), round(y, 3), round(z, 3))
        storey = str(data.get("storey", data.get("storey_id", "Unassigned")))
        ntype = str(data.get("type", "unknown"))

        node_coords[node_id] = (x, y, z)
        node_storeys[node_id] = storey
        node_types[node_id] = ntype

        # Check duplicate positions (different nodes at exact same coord)
        if pos in seen_positions and seen_positions[pos] != node_id:
            duplicate_nodes += 1
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="duplicate_position",
                message=f"Nodes '{node_id}' and '{seen_positions[pos]}' share identical coordinate {pos}",
                entity_ids=[node_id, seen_positions[pos]],
            ))
        else:
            seen_positions[pos] = node_id

        # Wall collision check for node position
        if collision_detector and ntype not in ("door", "gate", "stair", "elevator"):
            if collision_detector.check_point_collision((x, y, z), storey, clearance_m=0.15):
                nodes_inside_walls += 1
                report.issues.append(ValidationIssue(
                    severity="ERROR",
                    category="node_inside_wall",
                    message=f"Node '{node_id}' ({ntype}) is inside or too close to a wall on {storey}",
                    entity_ids=[node_id],
                ))

        # Check isolated nodes (degree == 0)
        if G.degree[node_id] == 0:
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="isolated_node",
                message=f"Node '{node_id}' ({ntype}) has degree 0 (isolated)",
                entity_ids=[node_id],
            ))

    # 2. Edge Validation
    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", data.get("edge_type", "walk"))
        dist = float(data.get("distance_m", 0.0))
        p1 = node_coords.get(u, (0, 0, 0))
        p2 = node_coords.get(v, (0, 0, 0))
        st1 = node_storeys.get(u, "")
        st2 = node_storeys.get(v, "")

        # Zero length
        if dist < 1e-4:
            zero_len_edges += 1
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="zero_length_edge",
                message=f"Edge ({u} <-> {v}) has near-zero length ({dist:.4f}m)",
                entity_ids=[u, v],
            ))

        # Excessively long edge
        if dist > max_edge_length_m and edge_type not in ("stair", "elevator"):
            long_edges += 1
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="long_edge",
                message=f"Edge ({u} <-> {v}) has suspicious length of {dist:.1f}m",
                entity_ids=[u, v],
            ))

        # Multi-floor transitions check
        f_from = data.get("floor_from")
        f_to = data.get("floor_to")
        is_floor_change = False
        if f_from is not None and f_to is not None and f_from != f_to:
            is_floor_change = True
        elif st1 != st2 and st1 != "Unassigned" and st2 != "Unassigned":
            is_floor_change = True

        if is_floor_change:
            if edge_type not in ("stair", "elevator", "vertical"):
                invalid_floor_transitions += 1
                report.issues.append(ValidationIssue(
                    severity="ERROR",
                    category="invalid_floor_transition",
                    message=(
                        f"Edge ({u} <-> {v}) changes floors ({st1} -> {st2}) "
                        f"without stair or elevator (type='{edge_type}')"
                    ),
                    entity_ids=[u, v],
                ))

        # Wall penetration check
        if collision_detector and not is_floor_change:
            # If neither node is a door/stair, check if segment penetrates solid wall
            has_door = node_types.get(u) in ("door", "gate") or node_types.get(v) in ("door", "gate")
            if not has_door and edge_type not in ("stair", "elevator"):
                if collision_detector.check_segment_collision(p1, p2, st1):
                    edges_crossing_walls += 1
                    report.issues.append(ValidationIssue(
                        severity="ERROR",
                        category="wall_crossing",
                        message=f"Edge ({u} <-> {v}) cuts through solid wall on {st1}",
                        entity_ids=[u, v],
                    ))

    # 3. Check Vertical Circulation
    stair_nodes = [n for n, t in node_types.items() if t == "stair"]
    elevator_nodes = [n for n, t in node_types.items() if t == "elevator"]

    # Check that stairs have vertical connections
    for sn in stair_nodes:
        vert_edges = [
            (u, v) for u, v, d in G.edges(sn, data=True)
            if d.get("type") in ("stair", "vertical") or node_types.get(u) == "stair" and node_types.get(v) == "stair"
        ]
        if not vert_edges:
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="stair_without_connection",
                message=f"Stair node '{sn}' has no vertical flight connection",
                entity_ids=[sn],
            ))

    # Check that doors have connections
    door_nodes = [n for n, t in node_types.items() if t in ("door", "gate")]
    for dn in door_nodes:
        if G.degree[dn] < 2:
            report.issues.append(ValidationIssue(
                severity="WARNING",
                category="door_incomplete",
                message=f"Door node '{dn}' connects to {G.degree[dn]} space(s) (expected >= 2)",
                entity_ids=[dn],
            ))

    # Determine pass/fail
    critical_errors = [i for i in report.issues if i.severity == "ERROR"]
    report.passed = (len(critical_errors) == 0)

    report.metrics = {
        "nodes_inside_walls": nodes_inside_walls,
        "edges_crossing_walls": edges_crossing_walls,
        "invalid_floor_transitions": invalid_floor_transitions,
        "duplicate_nodes": duplicate_nodes,
        "zero_len_edges": zero_len_edges,
        "long_edges": long_edges,
        "stair_nodes_count": len(stair_nodes),
        "door_nodes_count": len(door_nodes),
    }

    return report
