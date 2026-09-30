"""
main.py — CLI entry point for the IFC → 3D Model pipeline.

Usage
-----
    python src/main.py --input data/raw/<file>.ifc [--output-dir outputs] [--no-display]

Flags
-----
  --input       Path to the .ifc file (required)
  --output-dir  Directory for all outputs (default: outputs/)
  --no-display  Skip opening the interactive 3D window (headless mode)
  --types       Comma-separated IFC class whitelist, e.g. IfcWall,IfcSlab
  --max-elements  Limit extraction to N elements (smoke-test shortcut)
  --log-level   DEBUG | INFO | WARNING (default: INFO)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Make sure src/ is on the Python path when invoked directly ──────────────
sys.path.insert(0, str(Path(__file__).parent))

from load_ifc import load_and_validate, IFCLoadError
from extract_geometry import extract_all_elements, build_scene_graph, compute_global_bbox
from export_model import export_obj, export_glb, export_elements_json
from visualize import render_scene


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="IFC → 3D Model pipeline (Phase 1)",
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to the input .ifc file",
    )
    parser.add_argument(
        "--output-dir", "-o", default="outputs",
        help="Directory where outputs are written (default: outputs/)",
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="Suppress the interactive 3D window; still saves render.png",
    )
    parser.add_argument(
        "--types", default=None,
        help="Comma-separated IFC type whitelist, e.g. IfcWall,IfcSlab",
    )
    parser.add_argument(
        "--max-elements", type=int, default=None,
        help="Limit extraction to N elements (smoke-test mode)",
    )
    parser.add_argument(
        "--build-nav", action="store_true",
        help="Build physically-constrained multi-floor navigation graph and exports",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline orchestration
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(args: argparse.Namespace) -> int:
    """
    Execute all pipeline stages and return an exit code (0 = success).
    """
    t_start = time.perf_counter()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    include_types = None
    if args.types:
        include_types = [t.strip() for t in args.types.split(",") if t.strip()]

    # ── 1. Load & validate ──────────────────────────────────────────────────
    print("\n[1/5] Loading IFC file ...")
    try:
        ifc_file, metadata = load_and_validate(args.input)
    except (IFCLoadError, FileNotFoundError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    metadata.print_summary()

    # ── 2. Extract geometry ─────────────────────────────────────────────────
    print("\n[2/5] Extracting geometry ...")
    elements, failed = extract_all_elements(
        ifc_file,
        include_types=include_types,
        max_elements=args.max_elements,
    )

    if not elements:
        print("ERROR: No elements with geometry found. Aborting.", file=sys.stderr)
        return 1

    if failed:
        print(f"  WARNING: {len(failed)} element(s) failed geometry extraction (see DEBUG log)")

    # ── 3. Build scene graph ────────────────────────────────────────────────
    print("\n[3/5] Building scene graph …")
    scene_graph = build_scene_graph(elements)

    # Bounding box sanity check
    bbox = compute_global_bbox(elements)
    if bbox:
        bmin, bmax = bbox
        size = bmax - bmin
        print(f"\n  Bounding box  min: {bmin.round(2)}")
        print(f"                max: {bmax.round(2)}")
        print(f"                size (m): {size.round(2)}")

    # ── 4. Export ────────────────────────────────────────────────────────────
    print("\n[4/5] Exporting model ...")

    obj_path  = export_obj(elements,          output_dir / "model.obj")
    glb_path  = export_glb(elements,          output_dir / "model.glb")
    json_path = export_elements_json(elements, output_dir / "elements.json")

    print(f"  OK  OBJ  -> {obj_path}")
    print(f"  OK  GLB  -> {glb_path}")
    print(f"  OK  JSON -> {json_path}")

    # ── 5. Render ────────────────────────────────────────────────────────────
    print("\n[5/5] Rendering scene ...")
    screenshot_path = output_dir / "render.png"
    render_scene(
        elements,
        screenshot_path=screenshot_path,
        show_window=not args.no_display,
    )
    print(f"  OK  Screenshot -> {screenshot_path}")

    # ── 6. Navigation graph (optional) ───────────────────────────────────────
    if getattr(args, "build_nav", False):
        print("\n[6/6] Building physically-constrained navigation graph ...")
        from build_graph import build_graph_from_ifc
        build_graph_from_ifc(ifc_file, output_dir=output_dir)

    # -- Final summary --------------------------------------------------------
    elapsed = time.perf_counter() - t_start
    print(f"\n{'=' * 55}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"  Elements: {len(elements)} extracted, {len(failed)} failed")
    print(f"  Storeys : {metadata.storey_count}")
    print(f"  Outputs : {output_dir.resolve()}")
    print(f"{'=' * 55}\n")

    return 0


# ------------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    _configure_logging(args.log_level)
    sys.exit(run_pipeline(args))


if __name__ == "__main__":
    main()
