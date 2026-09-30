"""
cctv_integration.py  —  Phase 2: Map physical CCTV cameras onto the nav graph

Each camera has a world-space position, a direction vector, and a field-of-view
cone.  This module determines which graph nodes (spaces) fall inside each
camera's coverage area and registers that mapping for use by crowd_detection.py.

Usage
-----
    cameras = load_camera_config("cameras.json")
    camera_node_map = map_cameras_to_graph(cameras, G)
    # -> {"CAM_01": ["guid_room101", "guid_corridor_a"], ...}
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Camera data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CCTVCamera:
    """One physical CCTV camera."""
    id:               str
    label:            str               # human name, e.g. "Entrance Cam"
    position:         List[float]       # [x, y, z] IFC world coords
    direction:        List[float]       # [dx, dy, dz] unit vector pointing INTO scene
    fov_deg:          float  = 90.0    # horizontal field of view in degrees
    coverage_radius_m:float  = 8.0    # max detection distance
    storey:           str   = ""       # building storey this camera is on
    active:           bool  = True
    covered_nodes:    List[str] = field(default_factory=list)  # filled by mapper

    def covers_point(self, point: List[float]) -> bool:
        """Return True if the 3D point falls within this camera's cone."""
        cam  = np.array(self.position,  dtype=float)
        pt   = np.array(point,          dtype=float)
        dirv = np.array(self.direction, dtype=float)

        vec  = pt - cam
        dist = float(np.linalg.norm(vec))

        if dist > self.coverage_radius_m:
            return False
        if dist < 1e-6:
            return True   # point is at camera position

        # Angle between camera direction and vector to point
        norm_dir = dirv / (np.linalg.norm(dirv) + 1e-9)
        norm_vec = vec  / dist
        cos_angle = float(np.dot(norm_dir, norm_vec))
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))
        return angle_deg <= (self.fov_deg / 2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Camera config I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_camera_config(config_path: str | Path) -> List[CCTVCamera]:
    """
    Load camera definitions from a JSON file.

    Expected format:
    [
      {
        "id":       "CAM_01",
        "label":    "Entrance Camera",
        "position": [5.0, 0.5, 2.5],
        "direction":[0.0, 1.0, 0.0],
        "fov_deg":  90,
        "coverage_radius_m": 8.0,
        "storey": "0. kjeller"
      },
      ...
    ]
    """
    config_path = Path(config_path)
    if not config_path.exists():
        logger.warning("Camera config not found: %s — returning empty list", config_path)
        return []

    with config_path.open(encoding="utf-8") as f:
        raw = json.load(f)

    cameras = []
    for item in raw:
        try:
            cameras.append(CCTVCamera(**{k: v for k, v in item.items()
                                         if k in CCTVCamera.__dataclass_fields__}))
        except Exception as e:
            logger.warning("Skipping malformed camera entry: %s", e)

    logger.info("Loaded %d cameras from %s", len(cameras), config_path)
    return cameras


def save_camera_config(cameras: List[CCTVCamera], output_path: str | Path) -> Path:
    """Serialise camera list to JSON (covered_nodes included)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(c) for c in cameras], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Camera config saved -> %s", output_path)
    return output_path


def create_default_camera_config(
    G: nx.Graph,
    output_path: str | Path,
    cameras_per_storey: int = 2,
) -> List[CCTVCamera]:
    """
    Auto-generate placeholder camera positions from the graph nodes
    when no real camera config exists yet.  Places cameras near node
    centroids with a simple downward-looking direction.
    """
    # Group nodes by storey
    storey_nodes: Dict[str, list] = {}
    for guid, data in G.nodes(data=True):
        storey = data.get("storey", "Unassigned")
        storey_nodes.setdefault(storey, []).append((guid, data))

    cameras: List[CCTVCamera] = []
    cam_idx = 1

    for storey, node_list in sorted(storey_nodes.items()):
        # Pick evenly spaced nodes to place cameras at
        step = max(1, len(node_list) // cameras_per_storey)
        for i in range(0, min(len(node_list), cameras_per_storey * step), step):
            guid, data = node_list[i]
            centroid = data.get("centroid", [0, 0, 0])
            cam_pos = [centroid[0], centroid[1], centroid[2] + 2.5]  # 2.5m above space
            cameras.append(CCTVCamera(
                id=f"CAM_{cam_idx:02d}",
                label=f"{storey} Camera {cam_idx}",
                position=cam_pos,
                direction=[0.0, 0.0, -1.0],   # pointing straight down
                fov_deg=110.0,
                coverage_radius_m=6.0,
                storey=storey,
            ))
            cam_idx += 1

    save_camera_config(cameras, output_path)
    logger.info("Created %d default cameras", len(cameras))
    return cameras


# ─────────────────────────────────────────────────────────────────────────────
# Mapping cameras -> graph nodes
# ─────────────────────────────────────────────────────────────────────────────

def map_cameras_to_graph(
    cameras: List[CCTVCamera],
    G: nx.Graph,
) -> Dict[str, List[str]]:
    """
    For each camera, find all graph nodes whose centroid falls within the
    camera's coverage cone.  Mutates camera.covered_nodes in-place.

    Returns
    -------
    camera_node_map : {camera_id -> [node_guid, ...]}
    """
    camera_node_map: Dict[str, List[str]] = {}

    for cam in cameras:
        if not cam.active:
            camera_node_map[cam.id] = []
            continue

        covered = []
        for guid, data in G.nodes(data=True):
            centroid = data.get("centroid", [0, 0, 0])
            if cam.covers_point(centroid):
                covered.append(guid)
                # Tag the node with this camera
                existing = data.get("cameras", [])
                if cam.id not in existing:
                    existing.append(cam.id)
                    G.nodes[guid]["cameras"] = existing

        cam.covered_nodes = covered
        camera_node_map[cam.id] = covered
        logger.debug("Camera %s covers %d nodes", cam.id, len(covered))

    # Summary
    total_covered = len({g for nodes in camera_node_map.values() for g in nodes})
    logger.info(
        "Camera mapping: %d cameras covering %d/%d nodes",
        len(cameras), total_covered, G.number_of_nodes()
    )
    return camera_node_map


# ─────────────────────────────────────────────────────────────────────────────
# Coverage report
# ─────────────────────────────────────────────────────────────────────────────

def print_coverage_report(
    cameras: List[CCTVCamera],
    camera_node_map: Dict[str, List[str]],
    G: nx.Graph,
) -> None:
    print("\n+-- CCTV Coverage Report " + "-" * 34)
    for cam in cameras:
        nodes = camera_node_map.get(cam.id, [])
        names = [G.nodes[g].get("name", g[:8]) for g in nodes]
        status = "ON " if cam.active else "OFF"
        print(f"|  [{status}] {cam.id:<10} {cam.label:<25} covers: {', '.join(names) or '(none)'}")
    uncovered = [
        g for g in G.nodes
        if not G.nodes[g].get("cameras")
    ]
    print(f"|")
    print(f"|  Covered nodes   : {G.number_of_nodes() - len(uncovered)}/{G.number_of_nodes()}")
    print(f"|  Uncovered nodes : {len(uncovered)}")
    print("+" + "-" * 50)
