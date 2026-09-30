# Module: `dashboard/index.html`

**Browser-based 3D Building Viewer**

Source: [`dashboard/index.html`](../../dashboard/index.html)

---

## Responsibility

A single self-contained HTML file that opens directly in any modern browser (no server, no install). Provides a game-style interactive 3D viewer for the pipeline's output files — drag & drop an `.obj` or `.glb` onto the viewport and explore the building with orbit controls or WASD walk mode.

---

## How to Open

```powershell
# Double-click the file, or from terminal:
Start-Process "d:\IIT KGP\indoornav\dashboard\index.html"
```

Or open any browser and navigate to:
```
file:///d:/IIT KGP/indoornav/dashboard/index.html
```

> **Internet required on first load** — Three.js is fetched from `unpkg.com`. After the browser caches it, subsequent loads work offline.

---

## Loading a Model

### Drag & Drop
Drag `outputs\model.obj` or `outputs\model.glb` directly onto the 3D viewport.

### File Picker
Click **Open File** in the top bar → select the file.

### Supported Formats

| Format | IFC Type Colors | Storey Labels | Notes |
|---|---|---|---|
| `.obj` | ✅ Full palette | ✅ From group names | **Recommended** for this pipeline |
| `.glb` / `.gltf` | ⚠️ Vertex colors only | ⚠️ Shows "Loaded" | Best for external tools |

The OBJ format is preferred because the pipeline embeds IFC type and storey info in group names (`<storey>__<IfcType>`), which the viewer parses to apply the correct color and build the legend.

---

## Interface Layout

```
+----------------------------------------------------------+
|  Logo | Filename | Schema tag | Controls | FPS           |  <- Top bar
+--------+-------------------------------------------------+
|        |                                                 |
| Side   |            3D Viewport (Three.js)               |
| bar    |                                                 |
|        |   [Drag & Drop zone when no file loaded]        |
| Stats  |                                                 |
| Legend |                                                 |
| Floors |                                                 |
| Nav    |                                                 |
|        |                                                 |
+--------+-------------------------------------------------+
|  Orbit | Pan | Zoom | WASD | F=Fit | G=Grid | Coords     |  <- Bottom bar
+----------------------------------------------------------+
```

---

## Controls

### Orbit Mode (default)

| Input | Action |
|---|---|
| Left-click drag | Orbit (rotate around target) |
| Right-click drag | Pan (move target) |
| Scroll wheel | Zoom in / out |
| `F` | Fit entire scene to view |
| `G` | Toggle grid on/off |

### Walk Mode (game-style FPS)

Activate via **Walk Mode** button in the sidebar, or click in the viewport when walk mode is on.

| Input | Action |
|---|---|
| `W` / `Arrow Up` | Move forward |
| `S` / `Arrow Down` | Move backward |
| `A` / `Arrow Left` | Strafe left |
| `D` / `Arrow Right` | Strafe right |
| `Space` | Move up |
| `C` | Move down |
| `Shift` + any move | 3× speed |
| Mouse move | Look around (pointer locked) |
| `Esc` | Exit walk mode → return to orbit |

Walk mode uses the browser's **Pointer Lock API** — the cursor disappears and mouse movement controls the camera direction, exactly like an FPS game.

---

## Sidebar Panels

### Model Stats
- **Elements** — total mesh count loaded
- **IFC Types** — number of distinct IFC classes present
- **Storeys** — number of distinct building storeys
- **K Triangles** — total triangle count (÷1000)
- **Bounding Box** — Width × Depth × Height in metres

### IFC Types (Legend)
- Each IFC type shown with its color swatch and element count
- **Click any row** to toggle that type's visibility on/off
- Hidden types appear at 30% opacity in the legend

### Storeys
- Toggle switches for each building storey
- Click a row to show/hide all elements on that floor

### Navigation
- **Walk Mode** — enter FPS navigation (pulsing purple when active)
- **Top View** — bird's eye view
- **Front View** — elevation view
- **Isometric View** — standard 3D view

---

## Top Bar Controls

| Button | Action |
|---|---|
| **Open File** | File picker (alternative to drag & drop) |
| **Wireframe** | Toggle wireframe rendering on all meshes |
| **Auto Rotate** | Continuously rotate the scene around Y axis |
| **IFC Z→Y Fix** | Toggle −90° X rotation (ON by default for IFC Z-up files) |
| **Reset View** | Return camera to default isometric position |
| **Screenshot** | Save current viewport as PNG |

### IFC Z→Y Fix (important)

IFC world coordinates are **Z-up**, but Three.js/browsers use **Y-up**. This button applies a −90° rotation around the X axis to correct the orientation. It is **ON by default** because all pipeline outputs are in IFC Z-up coordinates.

> **Note**: As of 2026-08-23, `export_model.py` was updated to output Y-up coordinates directly. For those new exports, the Fix button should be toggled **OFF**. Old exports (pre-fix) still need it **ON**.

---

## IFC Type Color Palette

Same palette as `export_model.py` — colors are consistent between the pipeline screenshot and the viewer.

| IFC Type | Color |
|---|---|
| IfcWall / IfcWallStandardCase | Warm beige |
| IfcSlab | Cool grey |
| IfcColumn | Steel blue |
| IfcBeam | Navy blue |
| IfcDoor | Warm orange |
| IfcWindow | Sky blue |
| IfcRoof | Terracotta |
| IfcStair / IfcStairFlight | Tan |
| IfcRailing | Mid grey |
| IfcFurnishingElement | Light wood |
| IfcSite | Orange |
| IfcSpace | Vivid blue |
| Unknown types | MD5 hash-derived (deterministic) |

---

## Technical Stack

| Library | Version | CDN |
|---|---|---|
| Three.js | r128 | unpkg.com |
| OrbitControls | r128 (examples/js) | unpkg.com |
| OBJLoader | r128 (examples/js) | unpkg.com |
| GLTFLoader | r128 (examples/js) | unpkg.com |

Three.js r128 is used because it still ships the UMD global build (`three.min.js`) and the `examples/js/` folder, which work via `<script>` tags without a module bundler — making the single-file approach viable.

---

## Design Notes

- **Single-file**: everything (HTML, CSS, JS) in one file — no build step, no npm, no server
- **Dark gaming UI**: `#080d14` background, cyan `#00c8ff` accent, glassmorphism panels
- **Coordinate display**: real-time world coordinates under mouse cursor via raycasting
- **FPS counter**: updates every 500 ms
- **Shadow mapping**: PCFSoft shadows, 2048×2048 map, sun + fill light
- **Fog**: exponential depth fog matches the dark background for depth cues
