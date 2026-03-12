"""CAD export via cadquery (optional).

Exports MeshPart surface geometry to STEP or IGES format using cadquery.
cadquery is an optional dependency — functions raise ImportError with a
helpful message if it is not installed.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

import numpy as np

logger = logging.getLogger(__name__)

_CADQUERY_MISSING = (
    "cadquery is required for CAD export. "
    "Install with: pip install cadquery"
)


def _require_cadquery():
    """Check that cadquery is available."""
    try:
        import cadquery  # noqa: F401
        return cadquery
    except ImportError:
        raise ImportError(_CADQUERY_MISSING)


def mesh_to_step(
    vertices: np.ndarray,
    faces: np.ndarray,
    file_out: str,
) -> str:
    """Export a triangulated surface mesh to STEP format.

    Uses cadquery/OCP to create a BRep shell from triangles,
    then exports to STEP.

    Args:
        vertices: (N, 3) array of vertex coordinates.
        faces: (M, 3) array of triangle connectivity (0-based).
        file_out: Output STEP file path.

    Returns:
        Path to the written file.
    """
    cq = _require_cadquery()
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing
    from OCP.gp import gp_Pnt
    from OCP.TopoDS import TopoDS_Shell

    sewing = BRepBuilderAPI_Sewing()

    for face in faces:
        pts = [gp_Pnt(float(vertices[i, 0]),
                       float(vertices[i, 1]),
                       float(vertices[i, 2])) for i in face]

        # Create triangular face via wire
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire
        poly = BRepBuilderAPI_MakePolygon()
        for pt in pts:
            poly.Add(pt)
        poly.Close()

        if poly.IsDone():
            wire = poly.Wire()
            face_maker = BRepBuilderAPI_MakeFace(wire)
            if face_maker.IsDone():
                sewing.Add(face_maker.Face())

    sewing.Perform()
    shape = sewing.SewedShape()

    # Ensure .step extension
    stem, ext = os.path.splitext(file_out)
    if ext.lower() not in (".step", ".stp"):
        file_out = stem + ".step"

    os.makedirs(os.path.dirname(file_out) or ".", exist_ok=True)

    cq.exporters.export(cq.Workplane().add(shape), file_out, exportType="STEP")

    logger.info(f"Exported STEP: {file_out} ({len(faces)} faces)")
    return file_out


def mesh_to_iges(
    vertices: np.ndarray,
    faces: np.ndarray,
    file_out: str,
) -> str:
    """Export a triangulated surface mesh to IGES format.

    Args:
        vertices: (N, 3) array of vertex coordinates.
        faces: (M, 3) array of triangle connectivity (0-based).
        file_out: Output IGES file path.

    Returns:
        Path to the written file.
    """
    cq = _require_cadquery()
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Sewing
    from OCP.gp import gp_Pnt
    from OCP.IGESControl import IGESControl_Writer

    sewing = BRepBuilderAPI_Sewing()

    for face in faces:
        pts = [gp_Pnt(float(vertices[i, 0]),
                       float(vertices[i, 1]),
                       float(vertices[i, 2])) for i in face]

        poly = BRepBuilderAPI_MakePolygon()
        for pt in pts:
            poly.Add(pt)
        poly.Close()

        if poly.IsDone():
            wire = poly.Wire()
            face_maker = BRepBuilderAPI_MakeFace(wire)
            if face_maker.IsDone():
                sewing.Add(face_maker.Face())

    sewing.Perform()
    shape = sewing.SewedShape()

    # Ensure .iges extension
    stem, ext = os.path.splitext(file_out)
    if ext.lower() not in (".iges", ".igs"):
        file_out = stem + ".iges"

    os.makedirs(os.path.dirname(file_out) or ".", exist_ok=True)

    writer = IGESControl_Writer()
    writer.AddShape(shape)
    writer.ComputeModel()
    writer.Write(file_out)

    logger.info(f"Exported IGES: {file_out} ({len(faces)} faces)")
    return file_out


def export_mesh_part(
    mesh_part: "MeshPart",
    file_out: str,
    fmt: Literal["step", "iges"] = "step",
) -> str:
    """Export a MeshPart surface to STEP or IGES.

    Convenience wrapper that extracts vertices/faces from a MeshPart
    and calls the appropriate export function.

    Args:
        mesh_part: MeshPart with triangular surface elements.
        file_out: Output file path.
        fmt: Export format ("step" or "iges").

    Returns:
        Path to the written file.
    """
    _require_cadquery()

    if mesh_part.elements.count == 0:
        raise ValueError("MeshPart has no elements to export")

    # Convert to 0-based connectivity
    vertices = mesh_part.nodes.coords
    conn = mesh_part.elements.connectivity
    id_to_idx = {int(nid): i for i, nid in enumerate(mesh_part.nodes.ids)}
    faces = np.array([[id_to_idx[int(n)] for n in row] for row in conn],
                     dtype=np.int64)

    if fmt == "step":
        return mesh_to_step(vertices, faces, file_out)
    elif fmt == "iges":
        return mesh_to_iges(vertices, faces, file_out)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Use 'step' or 'iges'.")


def is_available() -> bool:
    """Check if cadquery is installed and CAD export is available."""
    try:
        import cadquery  # noqa: F401
        return True
    except ImportError:
        return False
