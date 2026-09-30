"""
visualize.py — Step 5: Color-coded 3D render + screenshot.

Primary backend : PyVista  (headless-capable, saves PNG directly)
Fallback backend: trimesh  (used if PyVista import fails)

The render is saved to outputs/render.png automatically.
If --no-display is NOT passed, an interactive window is also shown.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from extract_geometry import ElementData

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Deterministic per-type color palette
# ──────────────────────────────────────────────────────────────────────────────

_PALETTE: dict[str, tuple] = {
    "IfcWall":              (204, 191, 166),
    "IfcWallStandardCase":  (204, 191, 166),
    "IfcSlab":              (140, 140, 153),
    "IfcColumn":             (76, 140, 204),
    "IfcBeam":               (64, 115, 178),
    "IfcDoor":              (191, 128,  64),
    "IfcWindow":            (128, 204, 230),
    "IfcRoof":              (166,  89,  77),
    "IfcStair":             (178, 153, 102),
    "IfcStairFlight":       (178, 153, 102),
    "IfcRailing":           (102, 102, 102),
    "IfcFurnishingElement": (217, 178, 140),
    "IfcCovering":          (230, 224, 209),
    "IfcSpace":             ( 51, 153, 255),
    "IfcOpeningElement":    (255, 255, 255),
}


def _type_color_rgb(ifc_type: str) -> tuple:
    """Return an (R, G, B) tuple (0-255) for the given IFC type."""
    if ifc_type in _PALETTE:
        return _PALETTE[ifc_type]
    # Deterministic hash-based fallback for unknown types
    h = int(hashlib.md5(ifc_type.encode()).hexdigest(), 16)
    r = (h & 0xFF0000) >> 16
    g = (h & 0x00FF00) >> 8
    b = h & 0x0000FF
    return (max(80, r), max(80, g), max(80, b))


def _type_color_float(ifc_type: str) -> tuple:
    r, g, b = _type_color_rgb(ifc_type)
    return r / 255, g / 255, b / 255


# ──────────────────────────────────────────────────────────────────────────────
# PyVista render (primary)
# ──────────────────────────────────────────────────────────────────────────────

def _render_pyvista(
    elements: List[ElementData],
    screenshot_path: Path,
    show_window: bool,
) -> None:
    import pyvista as pv  # noqa: PLC0415

    pv.global_theme.background = "white"
    pv.global_theme.font.color = "black"

    plotter = pv.Plotter(
        off_screen=not show_window,
        window_size=[1920, 1080],
        title="IFC 3D Model — indoornav",
    )
    plotter.enable_anti_aliasing()
    plotter.add_light(pv.Light(position=(10, 10, 20), intensity=0.8))

    # Track which types we have already added to legend
    legend_entries: dict[str, tuple] = {}

    for elem in elements:
        if elem.vertices.shape[0] == 0 or elem.faces.shape[0] == 0:
            continue
        try:
            faces_col = np.hstack(
                [np.full((len(elem.faces), 1), 3, dtype=np.int32), elem.faces]
            )
            mesh = pv.PolyData(elem.vertices, faces_col.ravel())
            color = _type_color_float(elem.ifc_type)
            plotter.add_mesh(
                mesh,
                color=color,
                opacity=1.0,
                smooth_shading=True,
                show_edges=False,
            )
            if elem.ifc_type not in legend_entries:
                legend_entries[elem.ifc_type] = color
        except Exception as exc:
            logger.debug("PyVista skipped %s: %s", elem.guid, exc)

    # Add legend
    legend = [[t, [int(c * 255) for c in rgb]] for t, rgb in sorted(legend_entries.items())]
    if legend:
        plotter.add_legend(
            legend,
            bcolor=(0.95, 0.95, 0.95),
            border=True,
            size=(0.20, 0.40),
        )

    plotter.add_title("IFC Building Model", font_size=14, color="black")
    plotter.camera_position = "iso"
    plotter.reset_camera()

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    plotter.screenshot(str(screenshot_path), transparent_background=False)
    logger.info("Screenshot saved → %s", screenshot_path)

    if show_window:
        plotter.show()

    plotter.close()


# ──────────────────────────────────────────────────────────────────────────────
# trimesh fallback render
# ──────────────────────────────────────────────────────────────────────────────

def _render_trimesh(
    elements: List[ElementData],
    screenshot_path: Path,
    show_window: bool,
) -> None:
    import trimesh  # noqa: PLC0415

    scene = trimesh.Scene()
    for elem in elements:
        if elem.vertices.shape[0] == 0 or elem.faces.shape[0] == 0:
            continue
        try:
            r, g, b = _type_color_rgb(elem.ifc_type)
            mesh = trimesh.Trimesh(vertices=elem.vertices, faces=elem.faces, process=False)
            mesh.visual = trimesh.visual.ColorVisuals(
                mesh=mesh,
                vertex_colors=np.tile([r, g, b, 220], (len(elem.vertices), 1)),
            )
            scene.add_geometry(mesh)
        except Exception:
            pass

    # Save PNG via trimesh's offscreen renderer (pyglet / pyopengl)
    try:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        png_bytes = scene.save_image(resolution=(1920, 1080))
        if png_bytes:
            screenshot_path.write_bytes(png_bytes)
            logger.info("Screenshot saved (trimesh) → %s", screenshot_path)
    except Exception as exc:
        logger.warning("Could not save trimesh screenshot: %s", exc)

    if show_window:
        scene.show()


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def render_scene(
    elements: List[ElementData],
    screenshot_path: str | Path,
    *,
    show_window: bool = True,
) -> None:
    """
    Render the assembled scene, save a PNG screenshot.

    Tries PyVista first; falls back to trimesh if PyVista is unavailable.

    Parameters
    ----------
    elements        : flat list of ElementData from extract_geometry
    screenshot_path : path where the PNG will be written
    show_window     : if False, run fully headless (no GUI window opened)
    """
    screenshot_path = Path(screenshot_path)

    try:
        import pyvista  # noqa: PLC0415  (just check availability)
        logger.info("Using PyVista for rendering …")
        _render_pyvista(elements, screenshot_path, show_window)
    except ImportError:
        logger.warning("PyVista not available — falling back to trimesh renderer")
        _render_trimesh(elements, screenshot_path, show_window)
