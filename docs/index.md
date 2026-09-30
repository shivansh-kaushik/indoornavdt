# IndoorNav — IFC Pipeline Documentation

> **Phase 1**: IFC → 3D Model Reconstruction  
> Part of a larger digital-twin / seismic-risk-assessment workflow.

---

## Documentation Map

| Document | Description |
|---|---|
| [Architecture](architecture.md) | System design, data structures, key decisions |
| [Pipeline Walkthrough](pipeline.md) | Stage-by-stage trace with example console output |
| **Module Docs** | |
| [load_ifc.py](modules/load_ifc.md) | Stage 1 — Load & validate IFC file |
| [extract_geometry.py](modules/extract_geometry.md) | Stages 2–3 — Geometry extraction + scene graph |
| [export_model.py](modules/export_model.md) | Stage 4 — OBJ / GLB / JSON export |
| [visualize.py](modules/visualize.md) | Stage 5 — PyVista render + screenshot |

---

## Quick Run

```powershell
python src/main.py --input data/raw/<file>.ifc --no-display
```

Outputs land in `outputs/`: `model.obj`, `model.glb`, `elements.json`, `render.png`.

---

## Documentation Policy

> **Every code change must be reflected in the corresponding doc file before the PR is merged.**

- New function or class → update the relevant `docs/modules/*.md`
- New pipeline stage → update `docs/pipeline.md`
- Architecture change → update `docs/architecture.md`
- New CLI flag → update `docs/modules/main.md` and `README.md`

Docs live alongside source in version control — treat them as first-class artifacts.
