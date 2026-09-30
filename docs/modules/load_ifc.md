# Module: `load_ifc.py`

**Stage 1 of the pipeline — Load & Validate**

Source: [`src/load_ifc.py`](../../src/load_ifc.py)

---

## Responsibility

Open an IFC file with `ifcopenshell`, confirm it parses cleanly, extract top-level project metadata, and return a typed container to the orchestrator. This module knows nothing about geometry — it is purely concerned with file validity and project structure.

---

## Public API

### `load_and_validate(path)`

```python
def load_and_validate(path: str | Path) -> tuple[ifcopenshell.file, ProjectMetadata]
```

**Parameters**

| Name | Type | Description |
|---|---|---|
| `path` | `str` or `Path` | Absolute or relative path to the `.ifc` file |

**Returns**

| Item | Type | Description |
|---|---|---|
| `ifc_file` | `ifcopenshell.file` | Open IFC file object — pass directly to `extract_geometry` |
| `metadata` | `ProjectMetadata` | Typed container with project name, sites, buildings, storeys |

**Raises**

| Exception | When |
|---|---|
| `FileNotFoundError` | The path does not exist on disk |
| `IFCLoadError` | ifcopenshell cannot parse the file (corrupt, wrong format) |
| `IFCLoadError` | ifcopenshell is not installed |

---

### `ProjectMetadata`

```python
@dataclass
class ProjectMetadata:
    schema        : str        # "IFC2X3" | "IFC4" | "IFC4X3" …
    project_name  : str
    site_names    : List[str]
    building_names: List[str]
    storey_names  : List[str]
    filepath      : Path | None

    @property
    def storey_count(self) -> int: ...

    def print_summary(self) -> None: ...   # pretty-prints to stdout
```

### `IFCLoadError`

A subclass of `RuntimeError`. Raised for any condition that prevents the IFC file from being usable. Catch this at the top level to give the user a clean error message.

---

## How It Works

```
path
  │
  ▼
Path(path).resolve()  ──► FileNotFoundError if not exists
  │
  ▼
ifcopenshell.open(str(path))  ──► IFCLoadError on parse failure
  │
  ▼
ifc_file.schema  →  "IFC2X3" / "IFC4" / …
  │
  ├── ifc_file.by_type("IfcProject")    → project name
  ├── ifc_file.by_type("IfcSite")       → site names
  ├── ifc_file.by_type("IfcBuilding")   → building names
  └── ifc_file.by_type("IfcBuildingStorey") → storey names
  │
  ▼
return (ifc_file, ProjectMetadata(...))
```

---

## Schema Auto-Detection

`ifcopenshell.open()` handles both IFC2X3 and IFC4 transparently. After opening, `ifc_file.schema` contains the exact schema string. No configuration or flags needed.

Supported schemas:
- `IFC2X3` — legacy (pre-2013), most existing building stock
- `IFC4` — current standard
- `IFC4X1`, `IFC4X3` — newer variants, handled equally

---

## Design Notes

- `_safe_name(entity, fallback)` — all entity `.Name` accesses go through this helper which guards against `None`, whitespace-only, and missing attributes
- The `ifc_file` object returned here is the **live handle** — it remains open for the lifetime of the pipeline run; do not close it
- This module contains no geometry code and no numpy imports — it is intentionally thin

---

## Example Usage

```python
from load_ifc import load_and_validate, IFCLoadError

try:
    ifc_file, meta = load_and_validate("data/raw/building.ifc")
except IFCLoadError as e:
    print(f"Cannot load IFC: {e}")
    exit(1)

meta.print_summary()
print(f"Schema: {meta.schema}, {meta.storey_count} storeys")
```

---

## Console Output

```
──────────────────────────────────────────────────
  IFC Pipeline — Project Summary
──────────────────────────────────────────────────
  File       : D:\IIT KGP\indoornav\data\raw\example.ifc
  Schema     : IFC2X3
  Project    : Office Block A
  Sites      : Main Campus
  Buildings  : Block A
  Storeys    : 3  → Ground Floor, Level 1, Level 2
──────────────────────────────────────────────────
```
