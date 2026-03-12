"""File readers for various geodata formats.

Reads STL, OBJ, XYZ files into MeshPart objects.
Uses trimesh/meshio for robust parsing, with custom readers for XYZ.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart
from ..core.containers import ElementContainer

logger = logging.getLogger(__name__)


def read_stl(file_path: str, name: str = "MeshPart") -> MeshPart:
    """Read an STL file into a MeshPart.

    Handles duplicate vertices by merging them (STL stores vertices per-face).
    """
    import trimesh
    mesh = trimesh.load(file_path, file_type="stl", force="mesh")
    mp = MeshPart.from_trimesh(mesh, name=name)
    logger.info(f"Read STL: {mp.nodes.count} nodes, {mp.elements.count} elements from '{file_path}'")
    return mp


def read_obj(file_path: str, name: str = "MeshPart",
             extract_groups: bool = True) -> MeshPart:
    """Read an OBJ file into a MeshPart.

    If extract_groups=True, creates sub-parts for each 'o' object group.
    This handles the building import case where each building is a separate object.
    """
    mp = MeshPart(name=name)

    node_id = 1
    elem_id = 1
    current_sub: Optional[MeshPart] = None
    object_count = 0

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if not parts:
                continue

            if parts[0] == "v" and len(parts) >= 4:
                # Vertex: v x y z
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                except ValueError:
                    continue
                mp.create_node(node_id, x, y, z)
                if current_sub is not None:
                    current_sub.nodes.add(node_id, x, y, z)
                node_id += 1

            elif parts[0] == "f" and len(parts) >= 4:
                # Face: f v1 v2 v3 (or f v1/vt1/vn1 v2/vt2/vn2 v3/vt3/vn3)
                try:
                    face_nodes = []
                    for p in parts[1:4]:
                        # Handle v/vt/vn format
                        vi = int(p.split("/")[0])
                        face_nodes.append(vi)
                except (ValueError, IndexError):
                    continue

                mp.create_element("tri3", elem_id, face_nodes)
                if current_sub is not None:
                    current_sub.create_element("tri3", elem_id, face_nodes)
                    # Add nodes to sub-part if not already there
                    for nid in face_nodes:
                        if not current_sub.nodes.has_node(nid):
                            coords = mp.nodes.get_coords(nid)
                            current_sub.nodes.add(nid, coords[0], coords[1], coords[2])
                elem_id += 1

            elif parts[0] == "o" and extract_groups and len(parts) >= 2:
                # Object group
                group_name = parts[1]
                object_count += 1
                if "Building" in group_name or "building" in group_name:
                    sub_name = f"Building_{object_count}"
                else:
                    sub_name = f"Object_{object_count}"
                current_sub = mp.create_sub_part(sub_name)

    logger.info(f"Read OBJ: {mp.nodes.count} nodes, {mp.elements.count} elements, "
                f"{len(mp.sub_parts)} groups from '{file_path}'")
    return mp


def read_xyz(file_path: str, name: str = "MeshPart") -> MeshPart:
    """Read an XYZ point cloud file into a MeshPart (nodes only, no elements)."""
    mp = MeshPart(name=name)
    node_id = 1

    with open(file_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 3 and all(_is_float(p) for p in parts[:3]):
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                mp.create_node(node_id, x, y, z)
                node_id += 1

    logger.info(f"Read XYZ: {mp.nodes.count} nodes from '{file_path}'")
    return mp


def read_mesh(file_path: str, name: str = "MeshPart") -> MeshPart:
    """Generic mesh reader using meshio. Supports many formats (VTK, XDMF, etc.)."""
    import meshio

    mesh = meshio.read(file_path)
    mp = MeshPart(name=name)

    # Add nodes
    n_nodes = len(mesh.points)
    ids = np.arange(1, n_nodes + 1, dtype=np.int64)
    # Ensure 3D coordinates
    points = mesh.points
    if points.shape[1] == 2:
        points = np.column_stack([points, np.zeros(n_nodes)])
    mp.nodes.add_bulk(ids, points)

    # Add elements from cell blocks
    elem_id = 1
    for cell_block in mesh.cells:
        cell_type = cell_block.type
        connectivity = cell_block.data + 1  # meshio uses 0-based, we use 1-based IDs

        our_type = _meshio_to_type(cell_type)
        if our_type is None:
            logger.warning(f"Skipping unsupported cell type: {cell_type}")
            continue

        n_cells = len(connectivity)
        cell_ids = np.arange(elem_id, elem_id + n_cells, dtype=np.int64)
        mp.create_elements_bulk(our_type, cell_ids, connectivity)
        elem_id += n_cells

    # Import point data as node fields
    for key, data in mesh.point_data.items():
        mp.node_data[key] = data

    logger.info(f"Read mesh: {mp.nodes.count} nodes, {mp.elements.count} elements from '{file_path}'")
    return mp


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _meshio_to_type(meshio_type: str) -> Optional[str]:
    mapping = {
        "triangle": "tri3",
        "tetra": "tet4",
        "quad": "quad4",
        "hexahedron": "hex8",
        "line": "line2",
    }
    return mapping.get(meshio_type)
