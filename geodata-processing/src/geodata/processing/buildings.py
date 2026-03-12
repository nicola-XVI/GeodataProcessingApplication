"""Building processing utilities.

Port of geo_building.py: placement on terrain, filtering by boundary/height,
distance field computation from building hulls, and overlap splitting.

Replaces:
- GeoBuilding.ShiftBuildingOnTerrain
- GeoBuilding.DeleteBuildingsOutsideBoundary
- GeoBuilding.DeleteBuildingsUnderValue
- GeoBuilding.ComputeDistanceFieldFromHull
- GeoBuilding.FindDistanceFromTerrain
- BuildingUtilities.CheckIfInternal (C++)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Placement on terrain
# ---------------------------------------------------------------------------

def place_buildings_on_terrain(
    buildings: MeshPart,
    terrain: MeshPart,
    base_z_tolerance: float = 1e-5,
    remove_outside: bool = True,
) -> list[str]:
    """Place buildings on terrain using ray-plane intersection.

    For each building sub-part, identifies base nodes (z ~ 0), projects them
    vertically onto the terrain triangles, and shifts the building accordingly.
    Buildings whose base nodes fall outside the terrain are optionally removed.

    Port of GeoBuilding.ShiftBuildingOnTerrain + BuildingUtilities.CheckIfInternal.

    Args:
        buildings: MeshPart with building sub-parts (modified in-place).
        terrain: MeshPart with terrain surface (triangular elements).
        base_z_tolerance: Nodes with z < this are considered base nodes.
        remove_outside: If True, remove buildings with base nodes outside terrain.

    Returns:
        List of removed sub-part names (empty if remove_outside=False).
    """
    if terrain.elements.count == 0 or not buildings.sub_parts:
        return []

    # Build 2D Delaunay from terrain nodes for point location
    terrain_coords = terrain.nodes.coords
    terrain_2d = terrain_coords[:, :2]
    try:
        delaunay = Delaunay(terrain_2d)
    except Exception as e:
        logger.error(f"Failed to build terrain Delaunay: {e}")
        return []

    # Precompute terrain triangle data for ray-plane intersection
    terrain_conn = terrain.elements.connectivity  # node IDs
    terrain_id_to_idx = {int(nid): i for i, nid in enumerate(terrain.nodes.ids)}

    removed = []

    for sp_name in list(buildings.sub_parts.keys()):
        sp = buildings.get_sub_part(sp_name)
        if sp.nodes.count == 0:
            continue

        sp_coords = sp.nodes.coords
        sp_ids = sp.nodes.ids

        # Identify base nodes (z ~ 0)
        base_mask = sp_coords[:, 2] < base_z_tolerance

        if not base_mask.any():
            # No base nodes found; try shifting all nodes using KD-tree fallback
            _shift_building_kdtree(sp, buildings, terrain)
            continue

        base_coords = sp_coords[base_mask]
        base_ids = sp_ids[base_mask]

        # Find which terrain simplex contains each base node (2D)
        simplex_indices = delaunay.find_simplex(base_coords[:, :2])

        # Check if any base node is outside terrain
        outside_mask = simplex_indices < 0
        if outside_mask.any() and remove_outside:
            removed.append(sp_name)
            buildings.remove_sub_part(sp_name)
            continue

        # Compute Z on terrain for each base node via ray-plane intersection
        max_shift = 0.0
        base_shifts = {}  # node_id -> terrain_z

        for i, (bcoord, simplex_idx) in enumerate(zip(base_coords, simplex_indices)):
            if simplex_idx < 0:
                continue  # skip nodes outside terrain

            # Get terrain triangle vertices for this simplex
            terrain_z = _interpolate_z_on_triangle(
                bcoord[:2], delaunay, simplex_idx, terrain_coords, terrain_id_to_idx,
                terrain.nodes.ids, terrain_conn,
            )

            if terrain_z is not None:
                base_shifts[int(base_ids[i])] = terrain_z
                # Shift base node to terrain Z
                node_idx = sp.nodes.get_index(int(base_ids[i]))
                sp_coords[node_idx, 2] = terrain_z

                # Also update in parent
                nid = int(base_ids[i])
                if buildings.nodes.has_node(nid):
                    pidx = buildings.nodes.get_index(nid)
                    buildings.nodes.coords[pidx, 2] = terrain_z

                if terrain_z > max_shift:
                    max_shift = terrain_z

        # Shift roof nodes (z > tolerance) by max_shift
        roof_mask = ~base_mask
        for idx in np.where(roof_mask)[0]:
            nid = int(sp_ids[idx])
            sp_coords[idx, 2] += max_shift

            if buildings.nodes.has_node(nid):
                pidx = buildings.nodes.get_index(nid)
                buildings.nodes.coords[pidx, 2] = sp_coords[idx, 2]

    if removed:
        logger.info(f"Removed {len(removed)} buildings outside terrain")
    logger.info(f"Placed {len(buildings.sub_parts)} buildings on terrain")
    return removed


def _interpolate_z_on_triangle(
    point_2d: np.ndarray,
    delaunay: Delaunay,
    simplex_idx: int,
    terrain_coords: np.ndarray,
    id_to_idx: dict[int, int],
    node_ids: np.ndarray,
    connectivity: np.ndarray,
) -> Optional[float]:
    """Interpolate Z on a terrain triangle using barycentric coordinates.

    Uses the Delaunay simplex to identify which terrain triangle the point
    falls into, then interpolates Z from the triangle vertices.
    """
    # Delaunay simplices index into the points array
    simplex_verts = delaunay.simplices[simplex_idx]  # 3 indices into terrain_2d

    p0 = terrain_coords[simplex_verts[0]]
    p1 = terrain_coords[simplex_verts[1]]
    p2 = terrain_coords[simplex_verts[2]]

    # Barycentric coordinates in 2D
    v0 = p1[:2] - p0[:2]
    v1 = p2[:2] - p0[:2]
    v2 = point_2d - p0[:2]

    dot00 = v0 @ v0
    dot01 = v0 @ v1
    dot02 = v0 @ v2
    dot11 = v1 @ v1
    dot12 = v1 @ v2

    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-20:
        return None

    inv_denom = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
    v = (dot00 * dot12 - dot01 * dot02) * inv_denom

    # Interpolate Z
    return float(p0[2] + u * (p1[2] - p0[2]) + v * (p2[2] - p0[2]))


def _shift_building_kdtree(
    sp: MeshPart,
    buildings: MeshPart,
    terrain: MeshPart,
) -> None:
    """Fallback: shift a building using nearest terrain point (KD-tree).

    Used when no base nodes (z~0) are found.
    """
    terrain_tree = cKDTree(terrain.nodes.coords[:, :2])
    _, idx = terrain_tree.query(sp.nodes.coords[:, :2])
    terrain_z = terrain.nodes.coords[idx, 2]

    min_terrain_z = terrain_z.min()
    min_building_z = sp.nodes.coords[:, 2].min()
    dz = min_terrain_z - min_building_z

    sp.nodes.coords[:, 2] += dz

    for nid in sp.nodes.ids:
        nid = int(nid)
        if buildings.nodes.has_node(nid):
            buildings.nodes.coords[buildings.nodes.get_index(nid), 2] += dz


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def delete_buildings_outside_boundary(
    buildings: MeshPart,
    x_center: float,
    y_center: float,
    radius: float,
) -> list[str]:
    """Remove buildings outside a circular boundary.

    Port of GeoBuilding.DeleteBuildingsOutsideBoundary.

    A building is removed if ANY of its nodes is outside the circle.

    Args:
        buildings: MeshPart with building sub-parts (modified in-place).
        x_center, y_center: Center of the circular boundary.
        radius: Radius of the boundary.

    Returns:
        List of removed sub-part names.
    """
    removed = []

    for sp_name in list(buildings.sub_parts.keys()):
        sp = buildings.get_sub_part(sp_name)
        if sp.nodes.count == 0:
            removed.append(sp_name)
            buildings.remove_sub_part(sp_name)
            continue

        dists = np.sqrt(
            (sp.nodes.coords[:, 0] - x_center) ** 2
            + (sp.nodes.coords[:, 1] - y_center) ** 2
        )
        if (dists > radius).any():
            removed.append(sp_name)
            buildings.remove_sub_part(sp_name)

    if removed:
        logger.info(f"Removed {len(removed)} buildings outside boundary (r={radius})")
    return removed


def delete_buildings_under_value(
    buildings: MeshPart,
    z_value: float = 1e-7,
) -> list[str]:
    """Remove buildings that have any node at or below a Z threshold.

    Port of GeoBuilding.DeleteBuildingsUnderValue. Useful for removing
    buildings that were not properly shifted onto terrain.

    Args:
        buildings: MeshPart with building sub-parts (modified in-place).
        z_value: Z threshold. Buildings with any node z <= z_value are removed.

    Returns:
        List of removed sub-part names.
    """
    removed = []

    for sp_name in list(buildings.sub_parts.keys()):
        sp = buildings.get_sub_part(sp_name)
        if sp.nodes.count == 0:
            removed.append(sp_name)
            buildings.remove_sub_part(sp_name)
            continue

        if (sp.nodes.coords[:, 2] <= z_value).any():
            removed.append(sp_name)
            buildings.remove_sub_part(sp_name)

    if removed:
        logger.info(f"Removed {len(removed)} buildings under z={z_value}")
    return removed


# ---------------------------------------------------------------------------
# Distance field from building hull
# ---------------------------------------------------------------------------

def compute_distance_from_hull(
    domain: MeshPart,
    buildings: MeshPart,
    invert: bool = False,
    size_reduction: float = 0.0,
) -> np.ndarray:
    """Compute signed distance field from building hull surface.

    Port of GeoBuilding.ComputeDistanceFieldFromHull. Uses trimesh
    proximity instead of Kratos CalculateDistanceToSkinProcess3D.

    Args:
        domain: Volume mesh where distances are computed.
        buildings: Building surface mesh (hull).
        invert: If True, invert the distance field.
        size_reduction: Shift the distance field (positive = shrink buildings).

    Returns:
        (N,) array of signed distances at domain nodes.
        Also stored as node field "DISTANCE" on the domain.
    """
    import trimesh

    buildings_tm = buildings.to_trimesh(use_elements=True)
    if len(buildings_tm.faces) == 0:
        logger.warning("Empty building mesh, returning uniform distance")
        dist = np.ones(domain.nodes.count, dtype=np.float64) * 1000.0
        domain.set_node_field("DISTANCE", dist)
        return dist

    # Compute signed distance from domain nodes to building surface
    signed_dist = trimesh.proximity.signed_distance(buildings_tm, domain.nodes.coords)
    # trimesh: positive = inside, negative = outside
    # We want: negative = inside building, positive = outside (Kratos convention)
    distances = -signed_dist

    if invert:
        distances = -distances

    # Clamp extreme values (replacing +/- inf)
    distances = np.clip(distances, -20.0, 20.0)

    # Apply size reduction
    distances += size_reduction

    domain.set_node_field("DISTANCE", distances)

    # Verify zero-level exists
    has_pos = (distances > 0).any()
    has_neg = (distances < 0).any()
    if not (has_pos and has_neg):
        logger.warning("Distance field does not have zero-level inside the domain")

    logger.info(f"Computed distance from hull: min={distances.min():.3f}, "
                f"max={distances.max():.3f}")
    return distances


def add_distance_from_hull(
    domain: MeshPart,
    buildings: MeshPart,
    invert: bool = False,
    size_reduction: float = 0.0,
) -> np.ndarray:
    """Add (minimum) distance field from another building hull.

    Port of GeoBuilding.AddDistanceFieldFromHull. Takes the minimum
    between existing DISTANCE field and the new one, allowing
    accumulation of multiple building hulls.

    Args:
        domain: Volume mesh with existing "DISTANCE" field.
        buildings: Additional building surface mesh.
        invert: If True, invert the new distance field.
        size_reduction: Shift the new distance field.

    Returns:
        Updated (N,) distance array.
    """
    # Save existing distance before compute_distance_from_hull overwrites it
    existing = None
    if domain.has_node_field("DISTANCE"):
        existing = domain.get_node_field("DISTANCE").copy()

    new_dist = compute_distance_from_hull(
        domain, buildings, invert=invert, size_reduction=size_reduction,
    )

    if existing is not None:
        combined = np.minimum(existing, new_dist)
        domain.set_node_field("DISTANCE", combined)
        return combined

    return new_dist


# ---------------------------------------------------------------------------
# Terrain distance for buildings
# ---------------------------------------------------------------------------

def find_building_terrain_distances(
    buildings: MeshPart,
    terrain: MeshPart,
    base_z_tolerance: float = 1e-5,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Find Z-distances from buildings to terrain surface.

    Port of GeoBuilding.FindDistanceFromTerrain. For each building,
    computes the terrain Z at base node positions and returns
    coordinates of base and top nodes after shifting.

    Args:
        buildings: MeshPart with building sub-parts.
        terrain: Terrain surface mesh.
        base_z_tolerance: Nodes with z < this are considered base nodes.

    Returns:
        (base_coords_list, top_coords_list): Lists of (N,3) arrays,
        one per building, with shifted coordinates.
    """
    if terrain.elements.count == 0:
        return [], []

    terrain_coords = terrain.nodes.coords
    try:
        delaunay = Delaunay(terrain_coords[:, :2])
    except Exception:
        return [], []

    terrain_id_to_idx = {int(nid): i for i, nid in enumerate(terrain.nodes.ids)}

    base_coords_list = []
    top_coords_list = []

    for sp_name, sp in buildings.sub_parts.items():
        if sp.nodes.count == 0:
            continue

        sp_coords = sp.nodes.coords
        base_mask = sp_coords[:, 2] < base_z_tolerance

        if not base_mask.any():
            continue

        base_coords = sp_coords[base_mask]
        simplex_indices = delaunay.find_simplex(base_coords[:, :2])

        max_shift = 0.0
        base_shifted = []

        for i, (bcoord, simplex_idx) in enumerate(zip(base_coords, simplex_indices)):
            if simplex_idx < 0:
                continue
            terrain_z = _interpolate_z_on_triangle(
                bcoord[:2], delaunay, simplex_idx, terrain_coords,
                terrain_id_to_idx, terrain.nodes.ids, terrain.elements.connectivity,
            )
            if terrain_z is not None:
                base_shifted.append([bcoord[0], bcoord[1], terrain_z])
                if terrain_z > max_shift:
                    max_shift = terrain_z

        # Top nodes shifted by max_shift
        roof_mask = ~base_mask
        top_shifted = []
        for idx in np.where(roof_mask)[0]:
            top_shifted.append([
                sp_coords[idx, 0],
                sp_coords[idx, 1],
                sp_coords[idx, 2] + max_shift,
            ])

        if base_shifted:
            base_coords_list.append(np.array(base_shifted))
        if top_shifted:
            top_coords_list.append(np.array(top_shifted))

    return base_coords_list, top_coords_list
