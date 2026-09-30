# Pipeline Walkthrough

> End-to-end trace of a single run from `.ifc` file to final outputs.

---

## Running the Pipeline

```powershell
python src/main.py --input data/raw/example.ifc --no-display
```

---

## Stage 1 — Load & Validate

**Module**: [`load_ifc.py`](../src/load_ifc.py)

```
[1/5] Loading IFC file …
──────────────────────────────────────────────────
  IFC Pipeline — Project Summary
──────────────────────────────────────────────────
  File       : data/raw/example.ifc
  Schema     : IFC2X3
  Project    : My Building Project
  Sites      : Main Site
  Buildings  : Building A
  Storeys    : 3  → Ground Floor, Level 1, Level 2
──────────────────────────────────────────────────
```

**What happens:**
- `ifcopenshell.open(path)` parses the file and auto-detects the schema
- Top-level entities `IfcProject`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey` are queried
- A `ProjectMetadata` dataclass is returned to `main.py`
- Any parse failure raises `IFCLoadError` and the pipeline exits with code 1

---

## Stage 2 — Geometry Extraction

**Module**: [`extract_geometry.py`](../src/extract_geometry.py)

```
[2/5] Extracting geometry …
Extracting geometry: 100%|████████████| 847/847 [00:12<00:00, 67.3 elem/s]
  ⚠  3 element(s) failed geometry extraction (see DEBUG log)
```

**What happens:**
1. All `IfcProduct` entities are gathered (`ifc_file.by_type("IfcProduct")`)
2. Elements with no `Representation` are skipped (no geometry to extract)
3. For each remaining element, `ifcopenshell.geom.create_shape(settings, product)` is called
   - `USE_WORLD_COORDS = True` — positions are in absolute world space
   - Returns flat float arrays (`verts`) and int arrays (`faces`)
4. Arrays are reshaped to `(N, 3)` and stored in an `ElementData` dataclass
5. The storey is resolved by walking the spatial containment chain upward via `get_container()`
6. Elements that fail `create_shape()` are logged at DEBUG level and their GUIDs collected — the pipeline does **not** stop

**Key detail — world coordinates:**  
Every vertex is already transformed into the global coordinate system. No further matrix multiplication needed downstream.

---

## Stage 3 — Scene Graph Assembly

**Module**: [`extract_geometry.py`](../src/extract_geometry.py) → `build_scene_graph()`

```
[3/5] Building scene graph …

┌─ Element count by IFC type ──────────────────────────────────
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
└──────────────────────────────────────────────────────────────

  Bounding box  min: [ 0.     0.     0.  ]
                max: [42.50  18.30  12.60]
                size (m): [42.50  18.30  12.60]
```

**What happens:**
- Elements are grouped into `graph[storey][ifc_type]` — a `DefaultDict` of `DefaultDict`s
- The overall bounding box is computed and printed as a sanity check
  - A 42×18×12 m building is a reasonable 3-storey office — ✅
  - If bounding box extents are in mm instead of m (common IFC mistake), it would read ~42000 m — 🚩

---

## Stage 4 — Export

**Module**: [`export_model.py`](../src/export_model.py)

```
[4/5] Exporting model …
  ✓  OBJ  → outputs/model.obj
  ✓  GLB  → outputs/model.glb
  ✓  JSON → outputs/elements.json
```

### `model.obj`
- Groups named `<storey>__<ifc_type>` (e.g., `Ground_Floor__IfcWall`)
- GUID stored as a comment above each group for traceability
- 1-indexed faces (OBJ standard)
- Open in Blender / MeshLab / any OBJ viewer

### `model.glb`
- Binary glTF 2.0 via `trimesh.Scene.export(file_type="glb")`
- Each element is a separate geometry node named by GUID
- Vertex colors applied per IFC type (matching the render palette)
- Open at **https://gltf-viewer.donmccurdy.com** for instant web preview

### `elements.json`
- GUID → {ifc_type, storey, bbox} mapping
- No mesh data — stays small even for large buildings
- This is the **Phase 2 linkage layer** — structural/seismic models reference GUIDs back to geometry

---

## Stage 5 — Render

**Module**: [`visualize.py`](../src/visualize.py)

```
[5/5] Rendering scene …
  ✓  Screenshot → outputs/render.png
```

**What happens:**
- PyVista `Plotter(off_screen=True)` renders the scene headlessly
- Each IFC type gets a distinct color from the fixed palette (hash-based fallback for unknowns)
- Camera is set to isometric view (`camera_position = "iso"`)
- A legend mapping color → IFC type is added to the canvas
- Screenshot is saved at 1920×1080

**Color palette (subset):**

| IFC Type | Color |
|---|---|
| IfcWall | warm beige |
| IfcSlab | cool grey |
| IfcColumn | steel blue |
| IfcBeam | dark blue |
| IfcDoor | warm orange |
| IfcWindow | sky blue |
| IfcRoof | terracotta |
| IfcStair | tan |

---

## Final Console Summary

```
═══════════════════════════════════════════════════════
  Pipeline complete in 18.4s
  Elements: 710 extracted, 3 failed
  Storeys : 3
  Outputs : D:\IIT KGP\indoornav\outputs
═══════════════════════════════════════════════════════
```

---

## Output Files

| File | Use case |
|---|---|
| `outputs/model.obj` | Blender, MeshLab, local inspection |
| `outputs/model.glb` | Web viewer, Unity, Unreal, Three.js |
| `outputs/elements.json` | Phase 2 structural/seismic linkage |
| `outputs/render.png` | Quick visual sanity check, reports |

---

## Error Scenarios

| Scenario | Behaviour |
|---|---|
| File not found | `FileNotFoundError` → exit code 1 |
| Corrupt IFC | `IFCLoadError` → exit code 1 |
| Element has no geometry | Silently skipped, counted in summary |
| `create_shape()` fails | GUID logged at DEBUG, counted in "failed" |
| PyVista unavailable | Automatic fallback to trimesh renderer |
| No elements extracted | Pipeline aborts with error message |
