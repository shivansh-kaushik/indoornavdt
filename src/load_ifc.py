"""
load_ifc.py — Step 1: Load & Validate an IFC file.

Responsibilities:
  - Open the IFC file with ifcopenshell (auto-detects IFC2X3 / IFC4)
  - Extract and return project metadata
  - Raise IFCLoadError on fatal parse failures
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class IFCLoadError(RuntimeError):
    """Raised when an IFC file cannot be opened or parsed."""


@dataclass
class ProjectMetadata:
    """Lightweight container for top-level IFC project metadata."""

    schema: str                        # e.g. "IFC2X3" or "IFC4"
    project_name: str
    site_names: List[str] = field(default_factory=list)
    building_names: List[str] = field(default_factory=list)
    storey_names: List[str] = field(default_factory=list)
    filepath: Optional[Path] = None

    @property
    def storey_count(self) -> int:
        return len(self.storey_names)

    def print_summary(self) -> None:
        """Pretty-print project metadata to stdout."""
        sep = "-" * 52
        print(sep)
        print("  IFC Pipeline -- Project Summary")
        print(sep)
        print(f"  File       : {self.filepath}")
        print(f"  Schema     : {self.schema}")
        print(f"  Project    : {self.project_name}")
        print(f"  Sites      : {', '.join(self.site_names) or '(none)'}")
        print(f"  Buildings  : {', '.join(self.building_names) or '(none)'}")
        print(f"  Storeys    : {self.storey_count}  -> {', '.join(self.storey_names)}")
        print(sep)


def _safe_name(entity, fallback: str = "(unnamed)") -> str:
    """Return entity.Name, stripping whitespace; fall back gracefully."""
    try:
        name = entity.Name
        if name is not None:
            return str(name).strip() or fallback
    except AttributeError:
        pass
    return fallback


def load_and_validate(path: str | Path) -> tuple:
    """
    Open an IFC file, validate it, and extract project metadata.

    Parameters
    ----------
    path : str or Path
        Absolute or relative path to the .ifc file.

    Returns
    -------
    (ifc_file, metadata) : tuple
        ifc_file  — the open ifcopenshell.file object
        metadata  — ProjectMetadata instance

    Raises
    ------
    IFCLoadError
        If the file does not exist or ifcopenshell cannot parse it.
    FileNotFoundError
        If the path does not point to an existing file.
    """
    path = Path(path).resolve()

    if not path.exists():
        raise FileNotFoundError(f"IFC file not found: {path}")

    logger.info("Opening IFC file: %s", path)

    try:
        import ifcopenshell  # noqa: PLC0415  (imported here to give a clear error)
    except ImportError as exc:
        raise IFCLoadError(
            "ifcopenshell is not installed. Run: pip install ifcopenshell"
        ) from exc

    try:
        ifc_file = ifcopenshell.open(str(path))
    except Exception as exc:  # ifcopenshell raises generic Exception on bad files
        raise IFCLoadError(f"Failed to parse IFC file '{path}': {exc}") from exc

    schema = ifc_file.schema  # "IFC2X3" | "IFC4" | "IFC4X3" …

    # ---- project name --------------------------------------------------
    projects = ifc_file.by_type("IfcProject")
    project_name = _safe_name(projects[0]) if projects else "(no project entity)"

    # ---- sites ---------------------------------------------------------
    site_names = [_safe_name(s) for s in ifc_file.by_type("IfcSite")]

    # ---- buildings -----------------------------------------------------
    building_names = [_safe_name(b) for b in ifc_file.by_type("IfcBuilding")]

    # ---- building storeys ----------------------------------------------
    storey_names = [_safe_name(s) for s in ifc_file.by_type("IfcBuildingStorey")]

    metadata = ProjectMetadata(
        schema=schema,
        project_name=project_name,
        site_names=site_names,
        building_names=building_names,
        storey_names=storey_names,
        filepath=path,
    )

    logger.info(
        "Loaded IFC %s — project='%s', %d storey(s)",
        schema,
        project_name,
        metadata.storey_count,
    )
    return ifc_file, metadata
