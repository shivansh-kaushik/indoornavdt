# Module: `extract_geometry.py`

**Stages 2 & 3 of the pipeline — Geometry Extraction + Scene Graph**

Source: [`src/extract_geometry.py`](../../src/extract_geometry.py)

---

## Responsibility

Iterate over every `IfcProduct` entity in the IFC file, extract its triangulated mesh via `ifcopenshell.geom`, resolve which building storey it belongs to, and return both a flat list of typed element records and a nested scene graph for downstream use. Elements with missing or broken geometry are silently skipped — the pipeline never crashes.

---

## Public API

### `extract_all_elements(ifc_file, *, include_types, max_elements)`

```python
def extract_all_elements(
    ifc_file,
    *,
    include_types  : List[str] | None = None,
    max_elements   : int | None       = None,
) -> tuple[List[ElementData], List[str]]
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `ifc_file` | `ifcopenshell.file` | Live IFC handle from `load_and_validate()` |
| `include_types` | list of IFC class names | Whitelist filter, e.g. `["IfcWall", "IfcSlab"]`. `None` = extract all |
| `max_elements` | int | Hard limit on elements processed (smoke-test shortcut) |

**Returns**

| Item | Type | Description |
|---|---|---|
| `elements` | `List[ElementData]` | Successfully extracted elements |
| `failed_guids` | `List[str]` | GUIDs of elements where `create_shape()` raised an exception |

---

### `build_scene_graph(elements)`

```python
def build_scene_graph(elements: List[ElementData]) -> SceneGraph
```

Groups elements into a two-level nested dict keyed by storey then IFC type. Also prints the element-count summary table to stdout.

**Returns**

```python
SceneGraph = DefaultDict[str, DefaultDict[str, List[ElementData]]]
#            storey ──────────┘  ifc_type ──────┘
```

---

### `compute_global_bbox(elements)`

```python
def compute_global_bbox(elements: List[ElementData]) -> tuple[np.ndarray, np.ndarray] | None
```

Returns `(min_xyz, max_xyz)` across all elements. Returns `None` if the list is empty. Used in `main.py` for sanity-checking the building's physical scale.

---

## Data Structures

### `ElementData`

```python
@dataclass
class ElementData:
    guid     : str          # IFC GlobalId — globally unique per element
    ifc_type : str          # e.g. "IfcWall", "IfcSlab", "IfcColumn"
    storey   : str          # BuildingStorey name, or "Unassigned"
    vertices : np.ndarray   # shape (N, 3), dtype float32, world coordinates
    faces    : np.ndarray   # shape (F, 3), dtype int32, triangle indices (0-based)
    bbox_min : np.ndarray   # shape (3,), computed in __post_init__
    bbox_max : np.ndarray   # shape (3,), computed in __post_init__
```

> **Coordinate system**: All vertices are in world (absolute) coordinates because `USE_WORLD_COORDS = True` is set in the geometry settings. No additional matrix transforms are needed downstream.

---

## How Geometry Extraction Works

```
ifc_file.by_type("IfcProduct")
     │
     ▼ (filter by include_types if provided)
     │
     ├─ product.Representation is None? ──► skip (no geometry)
     │
     ▼
  ifcopenshell.geom.create_shape(settings, product)
     │
     ├─ exception? ──► log GUID at DEBUG, add to failed_guids, continue
     │
     ▼
  shape.geometry.verts  →  reshape(-1, 3)  →  vertices: np.ndarray (N, 3)
  shape.geometry.faces  →  reshape(-1, 3)  →  faces:    np.ndarray (F, 3)
     │
     ├─ empty arrays? ──► skip (degenerate geometry)
     │
     ▼
  _get_storey_name(product)
     │  walk get_container() up the spatial tree until IfcBuildingStorey
     ▼
  ElementData(guid, ifc_type, storey, vertices, faces)
     │
     ▼  appended to elements list
```

---

## Geometry Settings

```python
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)  # absolute world positions
settings.set(settings.WELD_VERTICES, True)     # merge duplicate vertices
```

`USE_WORLD_COORDS` is the most important setting — without it, each element's mesh would be in its own local coordinate system and would need the element's placement matrix applied manually.

---

## Storey Resolution (`_get_storey_name`)

IFC spatial containment is a tree: `IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey → IfcSpace → IfcProduct`. The helper `_get_storey_name()` walks up this chain using `ifcopenshell.util.element.get_container()` until it reaches an `IfcBuildingStorey`, then returns its name. If no storey is found (element is placed directly under Building or Site), it returns `"Unassigned"`.

---

## Element-Count Summary Table

Printed automatically by `build_scene_graph()`:

```
┌─ Element count by IFC type ──────────────────────────────────────
│  IfcWall                              312
│  IfcSlab                              148
│  IfcColumn                             64
│  IfcDoor                               54
│  IfcWindow                             48
│  IfcBeam                               32
│  IfcCovering                           28
│  IfcStairFlight                        12
│  IfcRailing                             8
│  IfcRoof                                4
│  TOTAL                                710
└──────────────────────────────────────────────────────────────────
```

---

## Error Handling Philosophy

- **Missing `Representation`** → silently skipped, not counted as failure  
- **`create_shape()` raises** → GUID added to `failed_guids`, logged at `DEBUG`; run continues  
- **Empty vertex/face arrays** → silently skipped  
- **Storey resolution fails** → element stored as `"Unassigned"`, never dropped  

The goal is that a single broken element never kills a 2-hour extraction run on a large building model.

---

## Design Notes

- `ElementData` holds raw numpy arrays, not `trimesh.Trimesh` objects. This keeps the extraction layer decoupled from any specific mesh library — `export_model.py` and `visualize.py` can each wrap it in whatever format they need.
- Bounding boxes are computed eagerly in `__post_init__` (one min/max pass over vertices). This is cheap and means callers don't have to recompute.
- `SceneGraph` uses `defaultdict(lambda: defaultdict(list))` so code that accesses `graph["Level 2"]["IfcColumn"]` never throws `KeyError` even if those keys don't exist.

---

## Example Usage

```python
from load_ifc import load_and_validate
from extract_geometry import extract_all_elements, build_scene_graph, compute_global_bbox

ifc_file, _ = load_and_validate("data/raw/building.ifc")

# Extract only walls and slabs
elements, failed = extract_all_elements(
    ifc_file,
    include_types=["IfcWall", "IfcSlab"],
)

scene_graph = build_scene_graph(elements)

# Access all walls on Ground Floor
walls_gf = scene_graph["Ground Floor"]["IfcWall"]
print(f"{len(walls_gf)} walls on Ground Floor")

bbox = compute_global_bbox(elements)
if bbox:
    bmin, bmax = bbox
    print(f"Building size: {(bmax - bmin).round(1)} m")
```
