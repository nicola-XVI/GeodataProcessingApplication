"""Boolean operations for mesh subtraction.

Replaces MMG isosurface discretization for building subtraction.
Uses trimesh boolean operations + gmsh re-tetrahedralization.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def subtract_buildings(
    domain: MeshPart,
    buildings: MeshPart,
    re_tetrahedralize: bool = True,
    min_size: float = 1.0,
    max_size: float = 50.0,
    repair: bool = True,
) -> MeshPart:
    """Subtract building geometry from the domain volume.

    Replaces MMG isosurface approach. Pipeline:
    1. Convert domain surface + buildings to trimesh
    2. Perform boolean difference
    3. Repair resulting mesh if needed
    4. Re-tetrahedralize the result

    Args:
        domain: Volume mesh (uses conditions as surface, or elements if tri3).
        buildings: Building surface mesh.
        re_tetrahedralize: If True, generate new tet mesh from the result.
        min_size: Min element size for re-tetrahedralization.
        max_size: Max element size for re-tetrahedralization.
        repair: If True, repair mesh before re-tetrahedralization.

    Returns:
        New MeshPart with buildings subtracted.
    """
    import trimesh

    # Convert to trimesh
    domain_tm = _mesh_part_to_trimesh_surface(domain)
    buildings_tm = buildings.to_trimesh(use_elements=True)

    if domain_tm is None or len(domain_tm.faces) == 0:
        logger.warning("Domain has no surface mesh for boolean operation")
        return domain

    if len(buildings_tm.faces) == 0:
        logger.warning("Buildings mesh is empty, returning domain unchanged")
        return domain

    # Repair inputs if needed
    if repair:
        domain_tm = _repair_mesh(domain_tm)
        buildings_tm = _repair_mesh(buildings_tm)

    # Boolean difference
    try:
        result_tm = trimesh.boolean.difference([domain_tm, buildings_tm])
    except Exception as e:
        logger.error(f"Boolean subtraction failed: {e}. Trying individual buildings.")
        result_tm = _subtract_individual_buildings(domain_tm, buildings, repair)

    if result_tm is None or len(result_tm.faces) == 0:
        logger.error("Boolean result is empty, returning original domain")
        return domain

    if repair:
        result_tm = _repair_mesh(result_tm)

    # Convert back to MeshPart
    result = MeshPart.from_trimesh(result_tm, name="Domain_Subtracted", as_elements=False)

    # Re-tetrahedralize if requested
    if re_tetrahedralize:
        with tempfile.TemporaryDirectory() as tmpdir:
            stl_path = str(Path(tmpdir) / "subtracted.stl")
            result_tm.export(stl_path, file_type="stl")

            from .tetrahedralization import tetrahedralize_from_stl
            result = tetrahedralize_from_stl(
                stl_path, min_size=min_size, max_size=max_size,
            )

    logger.info(f"Subtracted buildings: {result.nodes.count} nodes, "
                f"{result.elements.count} elements")
    return result


def subtract_building_by_distance(
    domain: MeshPart,
    buildings: MeshPart,
    distance_threshold: float = 0.0,
) -> None:
    """Mark/remove elements whose centroids are inside buildings using distance field.

    Alternative to boolean subtraction. Faster but less precise.

    Args:
        domain: Volume mesh (modified in-place).
        buildings: Building surface mesh.
        distance_threshold: Elements with signed distance < threshold are removed.
    """
    import trimesh

    buildings_tm = buildings.to_trimesh(use_elements=True)
    if len(buildings_tm.faces) == 0:
        return

    # Compute element centroids
    if domain.elements.count == 0:
        return

    conn = domain.elements.connectivity
    centroids = np.zeros((domain.elements.count, 3))
    for i in range(conn.shape[0]):
        for j in range(conn.shape[1]):
            nid = int(conn[i, j])
            centroids[i] += domain.nodes.get_coords(nid)
        centroids[i] /= conn.shape[1]

    # Compute signed distance from buildings
    signed_dist = trimesh.proximity.signed_distance(buildings_tm, centroids)

    # Mark elements inside buildings (negative signed distance)
    to_remove = signed_dist < distance_threshold
    if to_remove.any():
        keep_mask = ~to_remove
        domain.elements.remove_by_mask(keep_mask)
        for key in list(domain.element_data.keys()):
            domain.element_data[key] = domain.element_data[key][keep_mask]
        logger.info(f"Removed {to_remove.sum()} elements inside buildings")


def _mesh_part_to_trimesh_surface(mp: MeshPart):
    """Extract surface mesh from MeshPart as trimesh.Trimesh."""
    # Prefer conditions (surface faces), fall back to elements if tri3
    if mp.conditions.count > 0 and mp.conditions.element_type == "tri3":
        return mp.to_trimesh(use_elements=False)
    elif mp.elements.count > 0 and mp.elements.element_type == "tri3":
        return mp.to_trimesh(use_elements=True)
    return None


def _repair_mesh(mesh):
    """Attempt to repair a trimesh mesh for boolean operations."""
    import trimesh
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fill_holes(mesh)
    trimesh.repair.fix_winding(mesh)
    return mesh


def _subtract_individual_buildings(domain_tm, buildings: MeshPart, repair: bool):
    """Fallback: subtract buildings one at a time from the domain."""
    import trimesh

    result = domain_tm
    for sp_name, sp in buildings.sub_parts.items():
        if sp.elements.count == 0:
            continue
        building_tm = sp.to_trimesh(use_elements=True)
        if repair:
            building_tm = _repair_mesh(building_tm)
        try:
            result = trimesh.boolean.difference([result, building_tm])
        except Exception as e:
            logger.warning(f"Failed to subtract '{sp_name}': {e}, skipping")
            continue

    return result
