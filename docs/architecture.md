# Architecture Overview

> **Project**: `indoornav` — IFC → 3D Model Reconstruction  
> **Phase**: 1 (Parse IFC → Generate 3D Model)  
> **Last updated**: 2026-08-23  
> **Status**: Phase 1 complete and verified on `Grethes-hus-bok-2.ifc` (IFC2X3, 162 elements, 3 storeys)

---

## Goals

Build a clean, modular Python pipeline that:
1. Reads an IFC building file using **IfcOpenShell** (no custom parser)
2. Extracts triangulated geometry for every architectural/structural element
3. Assembles a storey-keyed scene graph preserving element metadata
4. Exports the model as `.obj` (Y-up), `.glb` (Y-up), and an `elements.json` linkage index
5. Renders a color-coded screenshot as a visual sanity check
6. Serves a **browser-based 3D viewer** (`dashboard/index.html`) with game-style WASD navigation

This is the **foundation layer** for a larger digital-twin / seismic-risk-assessment workflow. The architecture is intentionally layered so Phase 2+ modules (structural analysis, web viewer, simulation) can consume geometry without touching the parsing code.

---

## High-Level Design

```
+-------------------------------------------------------+
|                   main.py  (CLI)                      |
|     argparse -> orchestrates 5 pipeline stages        |
+------------------------+------------------------------+
                         |
          +--------------v--------------+
          |       load_ifc.py           |  Stage 1
          |  ifcopenshell.open()        |
          |  Schema auto-detect         |
          |  Returns: ifc_file +        |
          |           ProjectMetadata   |
          +--------------+--------------+
                         | ifc_file
          +--------------v--------------+
          |   extract_geometry.py       |  Stages 2-3
          |  ifcopenshell.geom          |
          |  USE_WORLD_COORDS=True      |
          |  Returns: List[ElementData] |
          |           SceneGraph        |
          +------+---------------+------+
                 |               |
    +------------v----+  +-------v--------------+
    | export_model.py |  |   visualize.py        |  Stage 4/5
    | .obj  .glb .json|  |  PyVista -> render.png|
    | (Y-up corrected)|  +----------------------+
    +-----------------+

                         +
    +--------------------v---------------------------+
    |       dashboard/index.html  (browser viewer)   |
    |  Three.js + OrbitControls + WASD walk mode     |
    |  Drag & drop .obj/.glb  |  IFC type colors     |
    |  Storey/type toggles    |  Screenshot          |
    +------------------------------------------------+
```

---

## Module Responsibilities

| Module | Stage | Input | Output | Side-effects |
|---|---|---|---|
|---|
| `load_ifc.py` | 1 | `.ifc` path | `ifc_file`, `ProjectMetadata` | Prints metadata table |
| `extract_geometry.py` | 2-3 | `ifc_file` | `List[ElementData]`, `SceneGraph` | Prints element-count table |
| `export_model.py` | 4 | `List[ElementData]` | `.obj`, `.glb`, `.json` (all Y-up) | None |
| `visualize.py` | 5 | `List[ElementData]` | `render.png` | Optional GUI window |
| `main.py` | — | CLI args | exit code | Orchestrates all stages |
| `dashboard/index.html` | viewer | `.obj` / `.glb` drag & drop | interactive 3D | Browser tab |

---

## Core Data Structures

### `ElementData` (from `extract_geometry.py`)

```python
@dataclass
class ElementData:
    guid     : str          # IFC GlobalId (unique per element)
    ifc_type : str          # e.g. "IfcWall", "IfcSlab"
    storey   : str          # BuildingStorey name or "Unassigned"
    vertices : np.ndarray   # shape (N, 3), float32, world coords
    faces    : np.ndarray   # shape (F, 3), int32, triangle indices
    bbox_min : np.ndarray   # shape (3,), auto-computed
    bbox_max : np.ndarray   # shape (3,), auto-computed
```

### `SceneGraph`

```python
SceneGraph = DefaultDict[str, DefaultDict[str, List[ElementData]]]
#            storey ──────────┘  ifc_type ──────┘
```

Enables floor-by-floor or type-by-type toggling in downstream viewers.

### `elements.json` schema

```json
{
  "<GUID>": {
    "ifc_type": "IfcWall",
    "storey":   "Level 1",
    "bbox": {
      "min":  [x, y, z],
      "max":  [x, y, z],
      "size": [dx, dy, dz]
    }
  }
}
```

No mesh data — intentionally lightweight for Phase 2 structural linkage.

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| IFC geometry | `ifcopenshell.geom.create_shape()` | No custom parser; handles IFC2X3 & IFC4 |
| Coordinate system | `USE_WORLD_COORDS = True` | Absolute placement needed for structural analysis |
| **Axis convention** | **Z-up (IFC) -> Y-up on export** | OBJ/GLB/glTF standard is Y-up; Blender & Three.js both expect Y-up |
| Mesh container | `numpy` arrays (not trimesh internally) | Decouples geometry from renderer/exporter |
| 3D export | OBJ (inspection) + GLB (web viewer) | Both cover the common toolchain |
| Visualization | PyVista (primary) + trimesh (fallback) | PyVista is headless-capable via `off_screen=True` |
| Error handling | Log + skip, never crash | Large IFC files always have some broken geometry |
| Scene graph key | `(storey, ifc_type)` | Natural split for future floor/type analysis |
| Web viewer | Single-file `dashboard/index.html` | No server needed; opens directly from disk in any browser |

---

## Dependency Map

```
ifcopenshell  ←── core IFC parsing + geometry
numpy         ←── vertex/face arrays
trimesh       ←── GLB/glTF assembly and export
pyvista       ←── 3D rendering + screenshot
vtk           ←── pyvista backend (auto-installed)
tqdm          ←── progress bars during extraction
pygltflib     ←── optional lower-level glTF manipulation
```

---

## Directory Layout

```
indoornav/
├── data/
│   └── raw/                    # input .ifc files
├── src/
│   ├── main.py                 # CLI entry point
│   ├── load_ifc.py             # Stage 1
│   ├── extract_geometry.py     # Stages 2-3
│   ├── export_model.py         # Stage 4 (Y-up axis corrected exports)
│   └── visualize.py            # Stage 5
├── dashboard/
│   └── index.html              # Browser 3D viewer (Three.js, no server needed)
├── outputs/                    # auto-created at runtime
│   ├── model.obj               # Y-up, groups named <storey>__<IfcType>
│   ├── model.glb               # Y-up binary glTF, vertex colours
│   ├── elements.json           # GUID -> {ifc_type, storey, bbox}
│   └── render.png              # PyVista color-coded screenshot
├── docs/
│   ├── index.md                # documentation home
│   ├── architecture.md         # <- this file
│   ├── pipeline.md             # end-to-end walkthrough
│   └── modules/
│       ├── load_ifc.md
│       ├── extract_geometry.md
│       ├── export_model.md
│       ├── visualize.md
│       └── dashboard.md        # web viewer docs
├── requirements.txt
└── README.md
```

---

## Extension Points (Phase 2+)

| Future module | Connects via |
|---|---|
| Structural / seismic analysis | `List[ElementData]` (numpy arrays) |
| Web-based digital twin viewer | `model.glb` + `elements.json` |
| Floor-level filtering | `SceneGraph[storey]` |
| Type-level filtering | `SceneGraph[storey][ifc_type]` |
| FEM mesh generation | `ElementData.vertices` / `.faces` directly |
| Property extraction | Extend `ElementData` with `properties: dict` |

The parsing layer (`load_ifc` + `extract_geometry`) is intentionally sealed — no analysis code should reach into it.

---

## Verified Run (Phase 1)

| Field | Value |
|---|---|
| Test file | `Grethes-hus-bok-2.ifc` (Norwegian residential house) |
| Schema | IFC2X3 |
| Project | `01-2019` / Grethes hus |
| Storeys | 3 (0. kjeller, 1. etasje, 2. etasje) |
| Elements extracted | 162 |
| Elements failed | 0 |
| Elements skipped (no geometry) | 7 |
| Pipeline runtime | ~18 s on a mid-range laptop |
| Bounding box | 44 m x 37 m x 10 m |
| Outputs | model.obj, model.glb, elements.json, render.png |
