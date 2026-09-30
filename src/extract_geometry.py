"""
extract_geometry.py — Steps 2 & 3: Geometry extraction and scene-graph assembly.

Responsibilities:
  - Iterate over all IfcProduct entities that have geometry via ifcopenshell.geom
  - Store per-element metadata (GUID, IFC type, storey, mesh, bbox)
  - Assemble a nested scene graph keyed by (storey, ifc_type)
  - Log and skip elements with missing/invalid geometry (never crash)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

BBox = Tuple[np.ndarray, np.ndarray]  # (min_xyz, max_xyz)


@dataclass
class ElementData:
    """All geometry + metadata for one IFC product."""

    guid: str
    ifc_type: str
    storey: str                        # name of IfcBuildingStorey (or "Unassigned")
    vertices: np.ndarray               # shape (N, 3), float32
    faces: np.ndarray                  # shape (F, 3), int32
    bbox_min: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    bbox_max: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))

    def __post_init__(self):
        if self.vertices.shape[0] > 0:
            self.bbox_min = self.vertices.min(axis=0)
            self.bbox_max = self.vertices.max(axis=0)


# Scene graph type: storey → ifc_type → list[ElementData]
SceneGraph = DefaultDict[str, DefaultDict[str, List[ElementData]]]


# ──────────────────────────────────────────────────────────────────────────────
# Helper: resolve storey for an element
# ──────────────────────────────────────────────────────────────────────────────

def _get_storey_name(element) -> str:
    """Walk up the spatial containment chain to find the building storey."""
    try:
        from ifcopenshell.util.element import get_container  # noqa: PLC0415
        container = get_container(element)
        while container is not None:
            if container.is_a("IfcBuildingStorey"):
                name = container.Name
                return str(name).strip() if name else "Unnamed Storey"
            # Try going up one more level
            try:
                from ifcopenshell.util.element import get_container as _gc  # noqa: PLC0415
                container = _gc(container)
            except Exception:
                break
    except Exception:
        pass
    return "Unassigned"


# ──────────────────────────────────────────────────────────────────────────────
# Core extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_all_elements(
    ifc_file,
    *,
    include_types: Optional[List[str]] = None,
    max_elements: Optional[int] = None,
) -> Tuple[List[ElementData], List[str]]:
    """
    Extract triangulated geometry for every IfcProduct with geometry.

    Parameters
    ----------
    ifc_file      : open ifcopenshell.file object
    include_types : optional whitelist of IFC class names (e.g. ["IfcWall"]). 
                    If None, all geometric products are extracted.
    max_elements  : optional hard limit (useful for quick smoke tests)

    Returns
    -------
    (elements, failed_guids)
        elements     — list of ElementData
        failed_guids — list of GUIDs whose geometry extraction failed
    """
    import ifcopenshell.geom as geom  # noqa: PLC0415

    settings = geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    # Triangulate; don't merge co-planar faces (keeps geometry clean)
    settings.set(settings.WELD_VERTICES, True)

    elements: List[ElementData] = []
    failed_guids: List[str] = []
    skipped_no_geom: int = 0

    # Build a flat list of IfcProduct entities to process
    products = ifc_file.by_type("IfcProduct")
    if include_types:
        products = [p for p in products if any(p.is_a(t) for t in include_types)]
    if max_elements is not None:
        products = products[:max_elements]

    total = len(products)
    logger.info("Processing %d IfcProduct entities …", total)

    try:
        from tqdm import tqdm  # noqa: PLC0415
        iterator = tqdm(products, desc="Extracting geometry", unit="elem")
    except ImportError:
        iterator = products

    for product in iterator:
        guid = product.GlobalId
        ifc_type = product.is_a()

        # Skip products that carry no geometric representation
        if not product.Representation:
            skipped_no_geom += 1
            continue

        try:
            shape = geom.create_shape(settings, product)
        except Exception as exc:
            logger.debug("Geometry failed for %s (%s): %s", guid, ifc_type, exc)
            failed_guids.append(guid)
            continue

        # ifcopenshell returns flat arrays — reshape them
        try:
            geom_data = shape.geometry
            verts_flat = np.array(geom_data.verts, dtype=np.float32)
            faces_flat = np.array(geom_data.faces, dtype=np.int32)

            if verts_flat.size == 0 or faces_flat.size == 0:
                skipped_no_geom += 1
                continue

            vertices = verts_flat.reshape(-1, 3)
            faces = faces_flat.reshape(-1, 3)
        except Exception as exc:
            logger.debug("Mesh reshape failed for %s: %s", guid, exc)
            failed_guids.append(guid)
            continue

        storey = _get_storey_name(product)

        elem = ElementData(
            guid=guid,
            ifc_type=ifc_type,
            storey=storey,
            vertices=vertices,
            faces=faces,
        )
        elements.append(elem)

    logger.info(
        "Extraction complete — %d elements extracted, %d failed, %d had no geometry",
        len(elements),
        len(failed_guids),
        skipped_no_geom,
    )
    return elements, failed_guids


# ──────────────────────────────────────────────────────────────────────────────
# Scene graph
# ──────────────────────────────────────────────────────────────────────────────

def build_scene_graph(elements: List[ElementData]) -> SceneGraph:
    """
    Group elements into a nested dict keyed by storey then IFC type.

    Returns
    -------
    scene_graph : DefaultDict[storey, DefaultDict[ifc_type, List[ElementData]]]
    """
    graph: SceneGraph = defaultdict(lambda: defaultdict(list))
    for elem in elements:
        graph[elem.storey][elem.ifc_type].append(elem)

    # Log a summary table
    _log_scene_graph_summary(graph)
    return graph


def _log_scene_graph_summary(graph: SceneGraph) -> None:
    """Print a table of element counts by storey and IFC type."""
    # Collect (ifc_type -> total count)
    type_counts: Dict[str, int] = defaultdict(int)
    for storey_data in graph.values():
        for ifc_type, elems in storey_data.items():
            type_counts[ifc_type] += len(elems)

    print("\n+-- Element count by IFC type " + "-" * 30)
    for ifc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"|  {ifc_type:<35} {count:>5}")
    print(f"|  {'TOTAL':<35} {sum(type_counts.values()):>5}")
    print("+" + "-" * 50)


# ──────────────────────────────────────────────────────────────────────────────
# Global bounding box
# ──────────────────────────────────────────────────────────────────────────────

def compute_global_bbox(elements: List[ElementData]) -> Optional[BBox]:
    """Return the overall (min_xyz, max_xyz) across all elements."""
    if not elements:
        return None
    mins = np.vstack([e.bbox_min for e in elements])
    maxs = np.vstack([e.bbox_max for e in elements])
    return mins.min(axis=0), maxs.max(axis=0)
