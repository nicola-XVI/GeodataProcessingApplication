"""Geometry import utilities.

Port of geo_importer.py: imports terrain and building geometry into MeshPart,
handling coordinate transforms, building grouping, and STL deduplication.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart
from ..io import readers
from .preprocessor import swap_yz_coordinates, shift, shift_to_center

logger = logging.getLogger(__name__)


def import_terrain(
    file_path: str,
    name: str = "Terrain",
    shift_to_origin: bool = True,
) -> tuple[MeshPart, float, float]:
    """Import terrain geometry from STL, OBJ, or XYZ file.

    Args:
        file_path: Path to terrain file.
        name: Name for the MeshPart.
        shift_to_origin: If True, shift centroid to (0, 0).

    Returns:
        (mesh_part, x_center, y_center): The imported MeshPart and
        the original centroid coordinates (for later coordinate recovery).
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".stl":
        mp = readers.read_stl(file_path, name=name)
    elif ext == ".obj":
        mp = readers.read_obj(file_path, name=name, extract_groups=False)
    elif ext == ".xyz":
        mp = readers.read_xyz(file_path, name=name)
    else:
        mp = readers.read_mesh(file_path, name=name)

    x_center, y_center = 0.0, 0.0
    if shift_to_origin:
        x_center, y_center = shift_to_center(mp)

    logger.info(f"Imported terrain '{name}': {mp.nodes.count} nodes, "
                f"{mp.elements.count} elements (shifted by {x_center:.1f}, {y_center:.1f})")
    return mp, x_center, y_center


def import_buildings(
    file_path: str,
    name: str = "Buildings",
    change_coordinates: bool = False,
    extract_groups: bool = True,
    x_shift: float = 0.0,
    y_shift: float = 0.0,
) -> MeshPart:
    """Import building geometry from OBJ or STL file.

    Args:
        file_path: Path to building file.
        name: Name for the MeshPart.
        change_coordinates: If True, swap Y/Z (for OSM2World OBJ files).
        extract_groups: If True, create sub-parts per building group.
        x_shift: X shift to apply (typically -x_center from terrain import).
        y_shift: Y shift to apply (typically -y_center from terrain import).

    Returns:
        MeshPart with buildings (sub-parts for each building if OBJ with groups).
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".obj":
        mp = readers.read_obj(file_path, name=name, extract_groups=extract_groups)
    elif ext == ".stl":
        mp = readers.read_stl(file_path, name=name)
    else:
        mp = readers.read_mesh(file_path, name=name)

    if change_coordinates:
        swap_yz_coordinates(mp)

    if x_shift != 0.0 or y_shift != 0.0:
        shift(mp, x_shift, y_shift, 0.0)

    logger.info(f"Imported buildings '{name}': {mp.nodes.count} nodes, "
                f"{mp.elements.count} elements, {len(mp.sub_parts)} groups")
    return mp


def add_geometry_to_mesh_part(
    target: MeshPart,
    source: MeshPart,
    as_sub_part: Optional[str] = None,
) -> None:
    """Add geometry from source MeshPart into target MeshPart.

    Handles ID offset to avoid collisions.

    Args:
        target: Destination MeshPart.
        source: Source MeshPart to add.
        as_sub_part: If provided, create a sub-part with this name in target.
    """
    # Compute ID offsets
    node_offset = target.nodes.max_id()
    elem_offset = target.elements.max_id()

    # Remap source IDs
    new_node_ids = source.nodes.ids + node_offset
    new_elem_ids = source.elements.ids + elem_offset if source.elements.count > 0 else np.empty(0, dtype=np.int64)

    # Add nodes
    target.create_nodes_bulk(new_node_ids, source.nodes.coords)

    # Add elements with remapped connectivity
    if source.elements.count > 0:
        new_conn = source.elements.connectivity + node_offset
        target.create_elements_bulk(
            source.elements.element_type,
            new_elem_ids,
            new_conn,
        )

    # Add conditions
    if source.conditions.count > 0:
        cond_offset = target.conditions.max_id()
        new_cond_ids = source.conditions.ids + cond_offset
        new_cond_conn = source.conditions.connectivity + node_offset
        target.create_conditions_bulk(
            source.conditions.element_type,
            new_cond_ids,
            new_cond_conn,
        )

    if as_sub_part:
        sub = target.create_sub_part(as_sub_part)
        for nid in new_node_ids:
            coords = target.nodes.get_coords(int(nid))
            sub.nodes.add(int(nid), coords[0], coords[1], coords[2])
        if source.elements.count > 0:
            for eid in new_elem_ids:
                conn = target.elements.get_node_ids(int(eid))
                sub.elements.add(int(eid), conn)

    logger.info(f"Added {source.nodes.count} nodes, {source.elements.count} elements "
                f"to '{target.name}'" + (f" as sub-part '{as_sub_part}'" if as_sub_part else ""))


def split_overlapping_buildings(mesh_part: MeshPart) -> int:
    """Split elements shared between multiple building sub-parts.

    Replaces BuildingUtilities::SplitBuilding. When buildings share nodes
    (overlapping geometry), duplicates the shared nodes so each building
    has independent geometry.

    Returns:
        Number of nodes duplicated.
    """
    if not mesh_part.sub_parts:
        return 0

    # Track which sub-part each node belongs to
    node_to_subparts: dict[int, list[str]] = {}
    for sp_name, sp in mesh_part.sub_parts.items():
        for nid in sp.nodes.ids:
            nid = int(nid)
            if nid not in node_to_subparts:
                node_to_subparts[nid] = []
            node_to_subparts[nid].append(sp_name)

    # Find shared nodes (belong to more than one sub-part)
    shared_nodes = {nid: sps for nid, sps in node_to_subparts.items() if len(sps) > 1}
    if not shared_nodes:
        return 0

    next_id = mesh_part.nodes.max_id() + 1
    duplicated = 0

    for nid, sub_part_names in shared_nodes.items():
        coords = mesh_part.nodes.get_coords(nid)

        # Keep original node for the first sub-part, duplicate for others
        for sp_name in sub_part_names[1:]:
            new_id = next_id
            next_id += 1

            # Create duplicate node in parent
            mesh_part.create_node(new_id, float(coords[0]), float(coords[1]), float(coords[2]))

            # Update sub-part: replace old node ID with new one
            sp = mesh_part.get_sub_part(sp_name)

            # Update element connectivity in sub-part
            if sp.elements.count > 0:
                mask = sp.elements.connectivity == nid
                sp.elements.connectivity[mask] = new_id

            # Update node in sub-part
            if sp.nodes.has_node(nid):
                sp.nodes.remove_by_ids({nid})
            sp.nodes.add(new_id, float(coords[0]), float(coords[1]), float(coords[2]))

            # Update element connectivity in parent for elements belonging to this sub-part
            if sp.elements.count > 0:
                for _, conn in sp.elements:
                    eid_parent = _  # element ID
                    if mesh_part.elements.has_element(eid_parent):
                        parent_conn = mesh_part.elements.get_node_ids(eid_parent)
                        parent_mask = parent_conn == nid
                        if parent_mask.any():
                            parent_conn[parent_mask] = new_id

            duplicated += 1

    logger.info(f"Split overlapping buildings: duplicated {duplicated} shared nodes")
    return duplicated


def delete_degenerate_elements(mesh_part: MeshPart) -> int:
    """Remove elements with duplicate nodes (degenerate triangles/tetrahedra).

    Replaces BuildingUtilities::DeleteNotValidElements.

    Returns:
        Number of elements removed.
    """
    if mesh_part.elements.count == 0:
        return 0

    conn = mesh_part.elements.connectivity
    # Check for duplicate node IDs within each element
    keep = np.ones(mesh_part.elements.count, dtype=bool)

    for i in range(conn.shape[0]):
        unique_nodes = np.unique(conn[i])
        if len(unique_nodes) < conn.shape[1]:
            keep[i] = False

    removed = int(np.sum(~keep))
    if removed > 0:
        mesh_part.elements.remove_by_mask(keep)
        # Also remove corresponding element data
        for key in list(mesh_part.element_data.keys()):
            mesh_part.element_data[key] = mesh_part.element_data[key][keep]
        logger.info(f"Removed {removed} degenerate elements")

    return removed
