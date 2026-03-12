"""File writers for various output formats.

Exports MeshPart to STL, OBJ, GLTF/GLB, VTK, and optionally STEP/IGES.
Uses trimesh for surface formats and meshio for volumetric/scientific formats.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def write_stl(mesh_part: MeshPart, file_path: str,
              use_elements: bool = True, binary: bool = True) -> None:
    """Write a MeshPart to STL format (surface mesh)."""
    trimesh_mesh = mesh_part.to_trimesh(use_elements=use_elements)
    if binary:
        trimesh_mesh.export(file_path, file_type="stl")
    else:
        trimesh_mesh.export(file_path, file_type="stl_ascii")
    logger.info(f"Wrote STL: {file_path}")


def write_obj(mesh_part: MeshPart, file_path: str,
              use_elements: bool = True, include_sub_parts: bool = False) -> None:
    """Write a MeshPart to OBJ format.

    If include_sub_parts=True, each sub-part becomes an 'o' object group.
    """
    container = mesh_part.elements if use_elements else mesh_part.conditions
    if container.count == 0:
        logger.warning(f"No {'elements' if use_elements else 'conditions'} to write")
        return

    # Build vertex mapping: node_id → sequential OBJ index (1-based)
    used_ids = container.get_all_node_ids()
    id_to_obj_idx = {int(nid): i + 1 for i, nid in enumerate(used_ids)}

    lines = [f"# Geodata Processing OBJ export"]
    lines.append(f"# {mesh_part.nodes.count} vertices, {container.count} faces")
    lines.append("")

    # Vertices
    for nid in used_ids:
        coords = mesh_part.nodes.get_coords(int(nid))
        lines.append(f"v {coords[0]:.10g} {coords[1]:.10g} {coords[2]:.10g}")

    lines.append("")

    if include_sub_parts and mesh_part.sub_parts:
        # Write faces grouped by sub-part
        for sp_name, sp in mesh_part.sub_parts.items():
            src = sp.elements if use_elements else sp.conditions
            if src.count == 0:
                continue
            lines.append(f"o {sp_name}")
            for _, conn in src:
                face_indices = " ".join(str(id_to_obj_idx[int(nid)]) for nid in conn)
                lines.append(f"f {face_indices}")
            lines.append("")
    else:
        # Write all faces
        for _, conn in container:
            face_indices = " ".join(str(id_to_obj_idx[int(nid)]) for nid in conn)
            lines.append(f"f {face_indices}")

    with open(file_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Wrote OBJ: {file_path}")


def write_gltf(mesh_part: MeshPart, file_path: str,
               use_elements: bool = True) -> None:
    """Write a MeshPart to GLTF/GLB format."""
    trimesh_mesh = mesh_part.to_trimesh(use_elements=use_elements)
    ext = Path(file_path).suffix.lower()
    if ext == ".glb":
        trimesh_mesh.export(file_path, file_type="glb")
    else:
        trimesh_mesh.export(file_path, file_type="gltf")
    logger.info(f"Wrote GLTF: {file_path}")


def write_vtk(mesh_part: MeshPart, file_path: str,
              include_node_data: bool = True) -> None:
    """Write a MeshPart to VTK format (supports volumetric data via meshio)."""
    import meshio

    # Build points array
    points = mesh_part.nodes.coords

    # Build cells
    cells = []
    if mesh_part.elements.count > 0:
        etype = mesh_part.elements.element_type
        meshio_type = _type_to_meshio(etype)
        # Convert node IDs in connectivity to 0-based indices
        conn = mesh_part.elements.connectivity.copy()
        for i in range(conn.shape[0]):
            for j in range(conn.shape[1]):
                conn[i, j] = mesh_part.nodes.get_index(int(conn[i, j]))
        cells.append(meshio.CellBlock(meshio_type, conn))

    if mesh_part.conditions.count > 0:
        ctype = mesh_part.conditions.element_type
        meshio_type = _type_to_meshio(ctype)
        conn = mesh_part.conditions.connectivity.copy()
        for i in range(conn.shape[0]):
            for j in range(conn.shape[1]):
                conn[i, j] = mesh_part.nodes.get_index(int(conn[i, j]))
        cells.append(meshio.CellBlock(meshio_type, conn))

    # Build point data
    point_data = {}
    if include_node_data:
        for key, arr in mesh_part.node_data.items():
            point_data[key] = arr

    mesh = meshio.Mesh(points=points, cells=cells, point_data=point_data)
    meshio.write(file_path, mesh)
    logger.info(f"Wrote VTK: {file_path}")


def write_xyz(mesh_part: MeshPart, file_path: str) -> None:
    """Write node coordinates to XYZ point cloud format."""
    with open(file_path, "w") as f:
        for _, x, y, z in mesh_part.nodes:
            f.write(f"{x} {y} {z}\n")
    logger.info(f"Wrote XYZ: {file_path}")


def write_auto(mesh_part: MeshPart, file_path: str, **kwargs) -> None:
    """Auto-detect format from file extension and write."""
    ext = Path(file_path).suffix.lower()
    writers = {
        ".stl": write_stl,
        ".obj": write_obj,
        ".gltf": write_gltf,
        ".glb": write_gltf,
        ".vtk": write_vtk,
        ".vtu": write_vtk,
        ".xyz": write_xyz,
    }
    writer = writers.get(ext)
    if writer is None:
        raise ValueError(f"Unsupported output format: {ext}. Supported: {list(writers.keys())}")
    writer(mesh_part, file_path, **kwargs)


def _type_to_meshio(our_type: str) -> str:
    mapping = {
        "tri3": "triangle",
        "tet4": "tetra",
        "quad4": "quad",
        "hex8": "hexahedron",
        "line2": "line",
    }
    if our_type not in mapping:
        raise ValueError(f"No meshio mapping for element type: {our_type}")
    return mapping[our_type]
