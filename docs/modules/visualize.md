# Module: `visualize.py`

**Stage 5 of the pipeline — Render & Screenshot**

Source: [`src/visualize.py`](../../src/visualize.py)

---

## Responsibility

Render the assembled 3D model with deterministic per-type coloring, save a screenshot as `render.png`, and optionally open an interactive 3D window. Tries **PyVista** first (headless-capable); falls back to **trimesh** if PyVista is not available.

---

## Public API

### `render_scene(elements, screenshot_path, *, show_window)`

```python
def render_scene(
    elements        : List[ElementData],
    screenshot_path : str | Path,
    *,
    show_window : bool = True,
) -> None
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `elements` | `List[ElementData]` | Flat list from `extract_all_elements()` |
| `screenshot_path` | `str` or `Path` | Where to save the PNG (parent dir auto-created) |
| `show_window` | bool | `True` = open interactive window after screenshot; `False` = headless |

Tries PyVista; silently falls back to trimesh if `import pyvista` fails.

---

## Backends

### Primary: PyVista

```python
plotter = pv.Plotter(off_screen=not show_window, window_size=[1920, 1080])
```

- Renders fully headless when `off_screen=True` (no display required)
- Saves screenshot via `plotter.screenshot(path)`
- Adds a legend mapping IFC type → color
- Anti-aliasing enabled
- Camera: isometric view, auto-fitted to scene bounds

### Fallback: trimesh

Used when PyVista import fails. Calls `scene.save_image(resolution=(1920, 1080))` which uses trimesh's built-in offscreen renderer (pyglet + PyOpenGL). Less reliable in fully headless environments, but useful for lightweight installations.

---

## Color System

### Fixed Palette (`_PALETTE`)

```python
_PALETTE = {
    "IfcWall":             (204, 191, 166),   # warm beige
    "IfcSlab":             (140, 140, 153),   # cool grey
    "IfcColumn":           ( 76, 140, 204),   # steel blue
    "IfcBeam":             ( 64, 115, 178),   # navy blue
    "IfcDoor":             (191, 128,  64),   # warm orange
    "IfcWindow":           (128, 204, 230),   # sky blue
    "IfcRoof":             (166,  89,  77),   # terracotta
    "IfcStair":            (178, 153, 102),   # tan
    "IfcRailing":          (102, 102, 102),   # mid grey
    "IfcFurnishingElement":(217, 178, 140),   # light wood
    "IfcCovering":         (230, 224, 209),   # off-white
    "IfcSpace":            ( 51, 153, 255),   # vivid blue
    "IfcOpeningElement":   (255, 255, 255),   # white
}
```

### Hash Fallback

For any IFC type not in `_PALETTE`, a color is generated from the MD5 hash of the type name:

```python
h = int(hashlib.md5(ifc_type.encode()).hexdigest(), 16)
r = max(80, (h & 0xFF0000) >> 16)  # minimum brightness = 80
g = max(80, (h & 0x00FF00) >> 8)
b = max(80, h & 0x0000FF)
```

The `max(80, ...)` floor prevents very dark colors that would be invisible against a white background. The hash is deterministic — the same IFC type always gets the same color, regardless of run order.

---

## PyVista Render Pipeline

```
List[ElementData]
     │
     ▼ (for each element)
  vertices → pv.PolyData(vertices, faces_with_count_prefix)
     │
  _type_color_float(ifc_type) → (R, G, B) in [0, 1]
     │
  plotter.add_mesh(mesh, color=..., smooth_shading=True)
     │
  legend_entries[ifc_type] = color  (deduplicated)
     │
     ▼
  plotter.add_legend(...)   → legend overlay
  plotter.camera_position = "iso"
  plotter.reset_camera()
     │
     ▼
  plotter.screenshot(path)  →  render.png  (1920×1080 PNG)
     │
     ▼ (if show_window=True)
  plotter.show()            →  interactive window
     │
  plotter.close()
```

> **PyVista face format**: `pv.PolyData` expects faces as a flat array where each polygon is prefixed with its vertex count. For triangles: `[3, i0, i1, i2, 3, i0, i1, i2, …]`. The code builds this with `np.hstack([np.full((len(faces), 1), 3), faces])`.

---

## Design Notes

- **Headless-first**: The default use case in CI / servers is `show_window=False`. PyVista with `off_screen=True` works without any display server (X11, Wayland) because VTK uses OSMesa for software rendering.
- **No global state**: The plotter is created and destroyed within `_render_pyvista()`. Multiple calls are safe.
- **Fallback is graceful**: If neither PyVista nor trimesh can save a screenshot (e.g., no OpenGL), the function logs a warning and continues — it does not crash the pipeline.
- **Same palette as export_model.py**: `_PALETTE` and `_IFC_TYPE_COLORS` in `export_model.py` use the same color values so the GLB and the screenshot look consistent.

---

## Example Usage

```python
from extract_geometry import extract_all_elements
from visualize import render_scene
from load_ifc import load_and_validate

ifc_file, _ = load_and_validate("data/raw/building.ifc")
elements, _ = extract_all_elements(ifc_file)

# Headless — just save the screenshot
render_scene(elements, "outputs/render.png", show_window=False)

# Interactive — open window AND save screenshot
render_scene(elements, "outputs/render.png", show_window=True)
```

---

## Headless Rendering on Windows

PyVista / VTK on Windows renders headlessly via the VTK software renderer — no extra setup required. The `off_screen=True` flag is sufficient.

On Linux servers without a display, you may need:
```bash
pip install pyvirtualdisplay
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
```
Or use Mesa's `LIBGL_ALWAYS_SOFTWARE=1` environment variable.
