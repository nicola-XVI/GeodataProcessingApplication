"""Terrain processing utilities.

Port of extrusion height, distance-from-ground, and terrain smoothing
from geo_mesher.py. Replaces C++ ExtrusionHeightUtilities.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart
from ..core.spatial import compute_extrusion_height, smooth_extrusion_height
from ..core.fields import (
    compute_distance_field_from_surface,
    compute_vertex_normals,
)

logger = logging.getLogger(__name__)


def set_extrusion_height(
    mesh_part: MeshPart,
    radius: float,
    height: float,
    free_board: float,
    smooth_iterations: int = 5,
) -> int:
    """Compute and apply extrusion height to mesh nodes.

    Port of geo_mesher.ComputeExtrusionHeight which calls
    ExtrusionHeightUtilities.SetExtrusionHeight + SmoothExtrusionHeight.

    Args:
        mesh_part: MeshPart with terrain nodes (modified in-place).
        radius: Domain radius for neighbor search.
        height: Maximum extrusion height above local minimum.
        free_board: Buffer zone for node removal threshold.
        smooth_iterations: Number of smoothing passes.

    Returns:
        Number of nodes removed.
    """
    coords = mesh_part.nodes.coords

    # Step 1: Compute raw extrusion heights
    heights, keep_mask = compute_extrusion_height(
        coords, radius=radius, max_height=height, free_board=free_board,
    )

    # Step 2: Smooth
    if smooth_iterations > 0:
        smooth_radius = radius / 5.0
        smooth_free_board = 0.8 * free_board
        heights = smooth_extrusion_height(
            coords, heights,
            radius=smooth_radius,
            iterations=smooth_iterations,
            free_board=smooth_free_board,
        )

    # Store as node field
    mesh_part.set_node_field("EXTRUSION_HEIGHT", heights)

    # Remove nodes above threshold
    removed = 0
    if not keep_mask.all():
        removed_ids = set(mesh_part.nodes.ids[~keep_mask].tolist())
        mesh_part.nodes.remove_by_mask(keep_mask)

        for key in list(mesh_part.node_data.keys()):
            mesh_part.node_data[key] = mesh_part.node_data[key][keep_mask]

        mesh_part._remove_elements_referencing(removed_ids)
        mesh_part._remove_conditions_referencing(removed_ids)
        removed = len(removed_ids)

    logger.info(f"Extrusion height set: removed {removed} nodes above threshold")
    return removed


def compute_distance_from_ground(mesh_part: MeshPart) -> np.ndarray:
    """Compute signed distance field from the ground surface.

    Port of geo_mesher.ComputeDistanceFieldFromGround.
    Uses BottomModelPart if available, otherwise identifies ground
    faces by downward-pointing normals.

    Args:
        mesh_part: MeshPart with volume mesh and conditions.

    Returns:
        (N,) array of distance values (negative near ground, positive above).
    """
    n_nodes = mesh_part.nodes.count
    distances = np.ones(n_nodes, dtype=np.float64)

    if mesh_part.has_sub_part("BottomModelPart"):
        # Use bottom sub-part nodes as ground
        bottom = mesh_part.get_sub_part("BottomModelPart")
        bottom_ids = set(int(nid) for nid in bottom.nodes.ids)

        for i, nid in enumerate(mesh_part.nodes.ids):
            if int(nid) in bottom_ids:
                distances[i] = -1e-7
    else:
        # Identify ground faces by downward-pointing normals
        if mesh_part.conditions.count > 0:
            conn_0based = _connectivity_to_0based(mesh_part)
            normals = compute_vertex_normals(mesh_part.nodes.coords, conn_0based)

            # Mark nodes on downward-facing conditions
            for cond_id, conn in mesh_part.conditions:
                # Compute face normal
                p = [mesh_part.nodes.get_coords(int(nid)) for nid in conn]
                face_normal = np.cross(p[1] - p[0], p[2] - p[0])
                length = np.linalg.norm(face_normal)
                if length > 1e-20:
                    face_normal /= length
                    # Downward-pointing: normal_z < -0.0001
                    if face_normal[2] < -0.0001:
                        for nid in conn:
                            idx = mesh_part.nodes.get_index(int(nid))
                            distances[idx] = -1e-7

    # Propagate distance field using fast marching
    try:
        import skfmm
        # Reshape to 1D signed field and solve eikonal equation
        # For unstructured meshes, use trimesh-based distance instead
        _propagate_distance_trimesh(mesh_part, distances)
    except ImportError:
        # Fallback: use simple BFS-like propagation
        _propagate_distance_simple(mesh_part, distances)

    mesh_part.set_node_field("DISTANCE_FROM_GROUND", distances)
    logger.info("Computed distance field from ground")
    return distances


def smooth_terrain_z(
    mesh_part: MeshPart,
    x_center: float,
    y_center: float,
    r_ground: float,
    r_boundary: float,
) -> None:
    """Smooth terrain Z-values towards a flat boundary.

    Creates a smooth transition from the terrain surface (within r_ground)
    to a flat surface at z_min (at r_boundary). Port of the Z-smoothing
    in MeshCircleWithTerrainPoints_old.

    Args:
        mesh_part: MeshPart with terrain nodes (modified in-place).
        x_center, y_center: Domain center coordinates.
        r_ground: Radius within which terrain is kept as-is.
        r_boundary: Radius at which terrain is fully flattened.
    """
    coords = mesh_part.nodes.coords
    z_min = coords[:, 2].min()

    dists = np.sqrt((coords[:, 0] - x_center) ** 2 + (coords[:, 1] - y_center) ** 2)

    # Smooth nodes between r_ground and r_boundary
    mask = dists > r_ground
    if mask.any():
        beta = 1.0 - (dists[mask] - r_ground) / (r_boundary - r_ground)
        beta = np.clip(beta, 0, 1)
        coords[mask, 2] = (coords[mask, 2] - z_min) * beta + z_min

    logger.info(f"Smoothed terrain Z: {mask.sum()} nodes adjusted")


def shift_buildings_on_terrain(
    buildings: MeshPart,
    terrain: MeshPart,
) -> None:
    """Vertically shift buildings so they sit on the terrain surface.

    For each building sub-part, finds the minimum terrain Z below the building
    and shifts the building down to that level.

    Args:
        buildings: MeshPart with building sub-parts (modified in-place).
        terrain: MeshPart with terrain surface.
    """
    from scipy.spatial import cKDTree

    if terrain.nodes.count == 0:
        return

    terrain_tree = cKDTree(terrain.nodes.coords[:, :2])

    for sp_name, sp in buildings.sub_parts.items():
        if sp.nodes.count == 0:
            continue

        # Find closest terrain point (2D) for each building node
        _, idx = terrain_tree.query(sp.nodes.coords[:, :2])
        terrain_z = terrain.nodes.coords[idx, 2]

        # Building sits at the minimum terrain Z below it
        min_terrain_z = terrain_z.min()
        min_building_z = sp.nodes.coords[:, 2].min()

        dz = min_terrain_z - min_building_z
        sp.nodes.coords[:, 2] += dz

        # Also shift in parent if nodes are shared
        for nid in sp.nodes.ids:
            nid = int(nid)
            if buildings.nodes.has_node(nid):
                buildings.nodes.coords[buildings.nodes.get_index(nid), 2] += dz

    logger.info(f"Shifted {len(buildings.sub_parts)} buildings onto terrain")


def _connectivity_to_0based(mesh_part: MeshPart) -> np.ndarray:
    """Convert conditions connectivity from node IDs to 0-based indices."""
    conn = mesh_part.conditions.connectivity.copy()
    for i in range(conn.shape[0]):
        for j in range(conn.shape[1]):
            conn[i, j] = mesh_part.nodes.get_index(int(conn[i, j]))
    return conn


def _propagate_distance_trimesh(mesh_part: MeshPart, distances: np.ndarray) -> None:
    """Propagate distance field using trimesh proximity."""
    import trimesh

    # Build surface from conditions
    if mesh_part.conditions.count == 0:
        return

    # Get ground face indices (where distance is negative)
    ground_node_ids = set()
    for i, d in enumerate(distances):
        if d < 0:
            ground_node_ids.add(int(mesh_part.nodes.ids[i]))

    if not ground_node_ids:
        return

    # Find conditions that have all nodes on the ground
    ground_faces = []
    for cid, conn in mesh_part.conditions:
        if all(int(nid) in ground_node_ids for nid in conn):
            face_0based = [mesh_part.nodes.get_index(int(nid)) for nid in conn]
            ground_faces.append(face_0based)

    if not ground_faces:
        return

    ground_mesh = trimesh.Trimesh(
        vertices=mesh_part.nodes.coords,
        faces=np.array(ground_faces),
    )

    # Compute signed distance from all nodes to ground surface
    signed = trimesh.proximity.signed_distance(ground_mesh, mesh_part.nodes.coords)
    # trimesh: negative = inside, positive = outside
    # We want: negative near ground, positive above
    distances[:] = -signed


def _propagate_distance_simple(mesh_part: MeshPart, distances: np.ndarray) -> None:
    """Simple distance propagation using nearest-neighbor from seed nodes."""
    from scipy.spatial import cKDTree

    seed_mask = distances < 0
    if not seed_mask.any():
        return

    seed_coords = mesh_part.nodes.coords[seed_mask]
    tree = cKDTree(seed_coords)

    non_seed = ~seed_mask
    if non_seed.any():
        dists, _ = tree.query(mesh_part.nodes.coords[non_seed])
        distances[non_seed] = dists
