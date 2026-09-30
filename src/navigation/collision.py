"""
collision.py — Physical wall extraction, 2D floor footprint indexing, and
rigorous collision validation for indoor navigation.

Enforces the invariant:
    WALLS ARE ABSOLUTE BARRIERS. A candidate path segment may only cross
    a wall footprint if it passes through an authorized door/portal aperture.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)


@dataclass
class DoorPortal:
    """Represents a traversable door or gate opening between spaces."""
    guid: str
    name: str
    storey: str
    storey_elevation: float
    position: List[float]       # [x, y, z] in IFC world coords
    width_m: float = 1.0
    aperture_polygon: Optional[Polygon] = None
    connected_spaces: List[str] = field(default_factory=list)


@dataclass
class WallGeometry:
    """Represents the physical 2D/3D geometry of an architectural wall."""
    guid: str
    name: str
    storey: str
    polygon_2d: Polygon | MultiPolygon   # Exact 2D footprint on XY plane
    solid_polygon: Polygon | MultiPolygon # Footprint with door openings subtracted
    bbox_min: List[float]
    bbox_max: List[float]


class WallCollisionDetector:
    """
    Spatial indexing and collision query engine for multi-storey buildings.
    Validates that navigation nodes and edges never penetrate solid walls.
    """

    def __init__(self):
        # Storey -> List[WallGeometry]
        self.walls_by_storey: Dict[str, List[WallGeometry]] = {}
        # Storey -> List[DoorPortal]
        self.doors_by_storey: Dict[str, List[DoorPortal]] = {}
        # Storey -> STRtree of solid wall polygons
        self.wall_trees: Dict[str, STRtree] = {}
        # Storey -> Map from tree geometry index to WallGeometry
        self.tree_wall_maps: Dict[str, List[WallGeometry]] = {}
        # Storey -> STRtree of door aperture polygons
        self.door_trees: Dict[str, STRtree] = {}
        # Storey -> Map from tree geometry index to DoorPortal
        self.tree_door_maps: Dict[str, List[DoorPortal]] = {}
        # Storey -> Combined solid wall MultiPolygon for fast batch queries
        self.solid_wall_unions: Dict[str, Polygon | MultiPolygon] = {}

    @classmethod
    def from_ifc(
        cls,
        ifc_file,
        door_aperture_radius_m: float = 0.85,
        default_clearance_m: float = 0.25,
    ) -> WallCollisionDetector:
        """
        Extract wall and door geometries from an open IFC file and build spatial indices.
        """
        import ifcopenshell.geom as geom

        detector = cls()
        settings = geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)

        # 1. Gather storey metadata mapping
        storey_names: Dict[str, str] = {}
        storey_elevs: Dict[str, float] = {}

        for st in ifc_file.by_type("IfcBuildingStorey"):
            s_name = str(st.Name).strip() if st.Name else "Storey"
            storey_names[st.GlobalId] = s_name
            elev = 0.0
            if hasattr(st, "Elevation") and st.Elevation is not None:
                elev = float(st.Elevation)
            storey_elevs[s_name] = elev

        # 2. Extract Doors & Portals
        doors_raw = ifc_file.by_type("IfcDoor")
        temp_doors_by_storey: Dict[str, List[DoorPortal]] = {}

        for door in doors_raw:
            dguid = door.GlobalId
            dname = str(door.Name).strip() if door.Name else f"Door_{dguid[:8]}"
            storey = _resolve_element_storey(door, ifc_file, storey_names)
            elev = storey_elevs.get(storey, 0.0)

            # Get 3D position
            pos = _get_entity_centroid(geom, settings, door)
            if pos is None:
                continue

            width = 1.0
            if hasattr(door, "OverallWidth") and door.OverallWidth:
                width = float(door.OverallWidth)
                if width > 50.0: # Millimetres to metres
                    width /= 1000.0

            # Door aperture in 2D (circle/box around door position)
            r = max(door_aperture_radius_m, width / 2.0 + 0.15)
            aperture_poly = Point(pos[0], pos[1]).buffer(r)

            portal = DoorPortal(
                guid=dguid,
                name=dname,
                storey=storey,
                storey_elevation=elev,
                position=pos,
                width_m=width,
                aperture_polygon=aperture_poly,
            )
            temp_doors_by_storey.setdefault(storey, []).append(portal)

        # 3. Extract Walls
        walls_raw = ifc_file.by_type("IfcWall") + ifc_file.by_type("IfcWallStandardCase")
        # Deduplicate by GlobalId
        seen_wall_guids: Set[str] = set()
        unique_walls = []
        for w in walls_raw:
            if w.GlobalId not in seen_wall_guids:
                seen_wall_guids.add(w.GlobalId)
                unique_walls.append(w)

        for wall in unique_walls:
            wguid = wall.GlobalId
            wname = str(wall.Name).strip() if wall.Name else f"Wall_{wguid[:8]}"
            storey = _resolve_element_storey(wall, ifc_file, storey_names)

            poly_2d, bmin, bmax = _extract_2d_wall_polygon(geom, settings, wall)
            if poly_2d is None or poly_2d.is_empty:
                continue

            # Subtract door openings located on this storey to produce the solid wall
            storey_door_polys = [
                d.aperture_polygon
                for d in temp_doors_by_storey.get(storey, [])
                if d.aperture_polygon and d.aperture_polygon.intersects(poly_2d)
            ]

            if storey_door_polys:
                door_union = unary_union(storey_door_polys)
                try:
                    solid_poly = poly_2d.difference(door_union)
                except Exception:
                    solid_poly = poly_2d
            else:
                solid_poly = poly_2d

            wall_geom = WallGeometry(
                guid=wguid,
                name=wname,
                storey=storey,
                polygon_2d=poly_2d,
                solid_polygon=solid_poly,
                bbox_min=bmin,
                bbox_max=bmax,
            )
            detector.walls_by_storey.setdefault(storey, []).append(wall_geom)

        detector.doors_by_storey = temp_doors_by_storey

        # 4. Build STRtrees and spatial caches
        all_storeys = set(detector.walls_by_storey.keys()) | set(detector.doors_by_storey.keys())
        for st in all_storeys:
            st_walls = detector.walls_by_storey.get(st, [])
            if st_walls:
                wall_geoms = [w.solid_polygon for w in st_walls if w.solid_polygon and not w.solid_polygon.is_empty]
                if wall_geoms:
                    detector.wall_trees[st] = STRtree(wall_geoms)
                    detector.tree_wall_maps[st] = [w for w in st_walls if w.solid_polygon and not w.solid_polygon.is_empty]
                    try:
                        detector.solid_wall_unions[st] = unary_union(wall_geoms)
                    except Exception:
                        detector.solid_wall_unions[st] = None

            st_doors = detector.doors_by_storey.get(st, [])
            if st_doors:
                door_geoms = [d.aperture_polygon for d in st_doors if d.aperture_polygon]
                if door_geoms:
                    detector.door_trees[st] = STRtree(door_geoms)
                    detector.tree_door_maps[st] = [d for d in st_doors if d.aperture_polygon]

        total_walls = sum(len(ws) for ws in detector.walls_by_storey.values())
        total_doors = sum(len(ds) for ds in detector.doors_by_storey.values())
        logger.info(
            "WallCollisionDetector initialized: %d walls, %d doors across %d storeys",
            total_walls, total_doors, len(all_storeys)
        )
        return detector

    def check_segment_collision(
        self,
        p1: List[float] | Tuple[float, ...],
        p2: List[float] | Tuple[float, ...],
        storey: str,
        ignore_door_guid: Optional[str] = None,
        penetration_tolerance_m: float = 0.08,
    ) -> bool:
        """
        Check if the line segment from p1 to p2 crosses any solid wall on the given storey.

        Parameters
        ----------
        p1, p2 : [x, y, (z)] coordinates
        storey : Storey identifier
        ignore_door_guid : Optional GUID of door whose aperture should be exempted
        penetration_tolerance_m : Distance tolerance for grazing contacts (m)

        Returns
        -------
        True if the segment penetrates a solid wall (BLOCKED), False if clear (PASS).
        """
        tree = self.wall_trees.get(storey)
        if not tree:
            return False

        seg_line = LineString([(p1[0], p1[1]), (p2[0], p2[1])])
        if seg_line.length < 1e-4:
            return False

        # Query tree for candidate intersecting wall geometries
        candidate_indices = tree.query(seg_line)
        if len(candidate_indices) == 0:
            return False

        wall_list = self.tree_wall_maps[storey]
        for idx in candidate_indices:
            wall_geom = wall_list[idx]
            solid_poly = wall_geom.solid_polygon
            if solid_poly.is_empty:
                continue

            # Fast bounding box test
            if not seg_line.intersects(solid_poly):
                continue

            # Calculate actual intersection
            try:
                inter = seg_line.intersection(solid_poly)
            except Exception:
                continue

            if inter.is_empty:
                continue

            # Check if intersection length exceeds penetration tolerance
            # (grazing contact at the boundary is not a wall crossing)
            inter_len = inter.length if hasattr(inter, "length") else 0.0
            if inter_len > penetration_tolerance_m:
                return True

            # If the intersection is a Point or MultiPoint, check if it truly cuts
            # into the interior of the solid wall
            if not inter.is_empty and solid_poly.buffer(-1e-3).intersects(seg_line):
                # Check intersection depth
                interior_inter = seg_line.intersection(solid_poly.buffer(-1e-3))
                if interior_inter.length > penetration_tolerance_m:
                    return True

        return False

    def check_point_collision(
        self,
        point: List[float] | Tuple[float, ...],
        storey: str,
        clearance_m: float = 0.25,
    ) -> bool:
        """
        Check if a 2D/3D point lies inside a wall or violates minimum clearance.
        Returns True if the point collides or is too close to a wall.
        """
        tree = self.wall_trees.get(storey)
        if not tree:
            return False

        pt_geom = Point(point[0], point[1])
        buffered_pt = pt_geom.buffer(clearance_m)

        candidate_indices = tree.query(buffered_pt)
        if len(candidate_indices) == 0:
            return False

        wall_list = self.tree_wall_maps[storey]
        for idx in candidate_indices:
            solid_poly = wall_list[idx].solid_polygon
            if solid_poly.is_empty:
                continue
            if solid_poly.intersects(buffered_pt):
                # If strictly inside or within clearance
                return True

        return False

    def get_doors_near_point(
        self,
        point: List[float] | Tuple[float, ...],
        storey: str,
        max_dist_m: float = 3.0,
    ) -> List[DoorPortal]:
        """Return all door portals within max_dist_m on the specified storey."""
        doors = self.doors_by_storey.get(storey, [])
        nearby = []
        for d in doors:
            dist = math.hypot(d.position[0] - point[0], d.position[1] - point[1])
            if dist <= max_dist_m:
                nearby.append(d)
        nearby.sort(key=lambda d: math.hypot(d.position[0] - point[0], d.position[1] - point[1]))
        return nearby


# ─────────────────────────────────────────────────────────────────────────────
# Geometry Extraction Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_entity_centroid(geom, settings, entity) -> Optional[List[float]]:
    try:
        shape = geom.create_shape(settings, entity)
        verts = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
        return verts.mean(axis=0).tolist()
    except Exception:
        return None


def _resolve_element_storey(element, ifc_file, storey_names: Dict[str, str]) -> str:
    """Find the BuildingStorey name that contains or aggregates this element."""
    # Method 1: IfcRelContainedInSpatialStructure
    for rel in ifc_file.by_type("IfcRelContainedInSpatialStructure"):
        try:
            if element in rel.RelatedElements:
                st = rel.RelatingStructure
                if st.is_a("IfcBuildingStorey"):
                    return storey_names.get(st.GlobalId, str(st.Name or "Storey"))
        except Exception:
            continue

    # Method 2: IfcRelAggregates
    for rel in ifc_file.by_type("IfcRelAggregates"):
        try:
            if element in rel.RelatedObjects:
                parent = rel.RelatingObject
                if parent.is_a("IfcBuildingStorey"):
                    return storey_names.get(parent.GlobalId, str(parent.Name or "Storey"))
        except Exception:
            continue

    return "Unassigned"


def _extract_2d_wall_polygon(
    geom, settings, wall
) -> Tuple[Optional[Polygon | MultiPolygon], List[float], List[float]]:
    """Extract the exact 2D footprint polygon (XY plane) and 3D bounds of a wall."""
    try:
        shape = geom.create_shape(settings, wall)
        verts = np.array(shape.geometry.verts, dtype=np.float32).reshape(-1, 3)
        faces = np.array(shape.geometry.faces, dtype=np.int32).reshape(-1, 3)
    except Exception:
        return None, [0, 0, 0], [0, 0, 0]

    if len(verts) == 0 or len(faces) == 0:
        return None, [0, 0, 0], [0, 0, 0]

    bmin = verts.min(axis=0).tolist()
    bmax = verts.max(axis=0).tolist()

    # Build 2D polygon from triangle projections
    triangles = []
    for face in faces:
        p0 = (float(verts[face[0], 0]), float(verts[face[0], 1]))
        p1 = (float(verts[face[1], 0]), float(verts[face[1], 1]))
        p2 = (float(verts[face[2], 0]), float(verts[face[2], 1]))
        poly = Polygon([p0, p1, p2])
        if poly.is_valid and poly.area > 1e-4:
            triangles.append(poly)

    if not triangles:
        # Fall back to 2D bounding box
        poly_2d = box(bmin[0], bmin[1], bmax[0], bmax[1])
        return poly_2d, bmin, bmax

    try:
        footprint = unary_union(triangles)
        # Clean small self-intersections or artifacts
        if not footprint.is_valid:
            footprint = footprint.buffer(0)
        return footprint, bmin, bmax
    except Exception:
        poly_2d = box(bmin[0], bmin[1], bmax[0], bmax[1])
        return poly_2d, bmin, bmax
