"""Point cloud and mesh preprocessing utilities.

Port of geo_preprocessor.py: Cut, Shift, height filters, coordinate transforms.
Operates on MeshPart objects with numpy-backed storage.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def cut_by_bounding_box(
    mesh_part: MeshPart,
    x_min: float = -np.inf,
    y_min: float = -np.inf,
    x_max: float = np.inf,
    y_max: float = np.inf,
    shift_to_origin: bool = False,
) -> int:
    """Remove nodes outside a 2D bounding box.

    Args:
        mesh_part: MeshPart to filter (modified in-place).
        x_min, y_min, x_max, y_max: Bounding box limits.
        shift_to_origin: If True, translate remaining nodes so (x_min, y_min) → (0, 0).

    Returns:
        Number of nodes removed.
    """
    coords = mesh_part.nodes.coords
    if mesh_part.nodes.count == 0:
        return 0

    keep = (
        (coords[:, 0] >= x_min) & (coords[:, 0] <= x_max) &
        (coords[:, 1] >= y_min) & (coords[:, 1] <= y_max)
    )
    removed = int(np.sum(~keep))

    if removed > 0:
        removed_ids = set(mesh_part.nodes.ids[~keep].tolist())
        mesh_part.nodes.remove_by_mask(keep)

        # Update node data fields
        for key in list(mesh_part.node_data.keys()):
            mesh_part.node_data[key] = mesh_part.node_data[key][keep]

        # Remove elements/conditions referencing removed nodes
        mesh_part._remove_elements_referencing(removed_ids)
        mesh_part._remove_conditions_referencing(removed_ids)

        logger.info(f"Cut: removed {removed} nodes outside bounding box")

    if shift_to_origin and mesh_part.nodes.count > 0:
        shift(mesh_part, -x_min, -y_min, 0.0)

    return removed


def shift(mesh_part: MeshPart, dx: float, dy: float, dz: float = 0.0) -> None:
    """Translate all nodes by (dx, dy, dz)."""
    if mesh_part.nodes.count == 0:
        return
    mesh_part.nodes.coords[:, 0] += dx
    mesh_part.nodes.coords[:, 1] += dy
    mesh_part.nodes.coords[:, 2] += dz
    logger.info(f"Shifted by ({dx}, {dy}, {dz})")


def shift_to_center(mesh_part: MeshPart) -> tuple[float, float]:
    """Shift nodes so the centroid (x, y) is at the origin.

    Returns the (x_center, y_center) that was subtracted.
    """
    if mesh_part.nodes.count == 0:
        return 0.0, 0.0
    x_center = float(mesh_part.nodes.coords[:, 0].mean())
    y_center = float(mesh_part.nodes.coords[:, 1].mean())
    shift(mesh_part, -x_center, -y_center, 0.0)
    return x_center, y_center


def filter_by_height(
    mesh_part: MeshPart,
    min_height: Optional[float] = None,
    max_height: Optional[float] = None,
) -> int:
    """Remove nodes outside a height (Z) range.

    Replaces ExtractValley (max_height) and ExtractMountain (min_height).

    Returns:
        Number of nodes removed.
    """
    if mesh_part.nodes.count == 0:
        return 0

    coords = mesh_part.nodes.coords
    keep = np.ones(mesh_part.nodes.count, dtype=bool)

    if min_height is not None:
        keep &= coords[:, 2] >= min_height
    if max_height is not None:
        keep &= coords[:, 2] <= max_height

    removed = int(np.sum(~keep))
    if removed > 0:
        removed_ids = set(mesh_part.nodes.ids[~keep].tolist())
        mesh_part.nodes.remove_by_mask(keep)

        for key in list(mesh_part.node_data.keys()):
            mesh_part.node_data[key] = mesh_part.node_data[key][keep]

        mesh_part._remove_elements_referencing(removed_ids)
        mesh_part._remove_conditions_referencing(removed_ids)

        logger.info(f"Height filter: removed {removed} nodes")

    return removed


def swap_yz_coordinates(mesh_part: MeshPart) -> None:
    """Swap Y and Z coordinates (Y=-Z_old, Z=Y_old).

    Used for OSM2World OBJ files where coordinate convention differs.
    """
    if mesh_part.nodes.count == 0:
        return
    coords = mesh_part.nodes.coords
    old_y = coords[:, 1].copy()
    old_z = coords[:, 2].copy()
    coords[:, 1] = -old_z
    coords[:, 2] = old_y
    logger.info("Swapped Y/Z coordinates")


def remove_duplicate_nodes(
    mesh_part: MeshPart,
    tolerance: float = 1e-8,
) -> int:
    """Merge duplicate nodes within tolerance distance.

    STL files store vertices per-face, creating many duplicates.
    Uses KD-tree for efficient duplicate detection.

    Returns:
        Number of duplicate nodes removed.
    """
    from scipy.spatial import cKDTree

    if mesh_part.nodes.count < 2:
        return 0

    coords = mesh_part.nodes.coords
    tree = cKDTree(coords)
    pairs = tree.query_pairs(r=tolerance)

    if not pairs:
        return 0

    # Build union-find to group duplicates
    parent = {int(nid): int(nid) for nid in mesh_part.nodes.ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    ids = mesh_part.nodes.ids
    for i, j in pairs:
        union(int(ids[i]), int(ids[j]))

    # Identify nodes to remove (keep the root of each group)
    to_remove = set()
    remap = {}
    for nid in ids:
        nid = int(nid)
        root = find(nid)
        if nid != root:
            to_remove.add(nid)
            remap[nid] = root

    if not to_remove:
        return 0

    # Remap connectivity in elements and conditions
    for container in [mesh_part.elements, mesh_part.conditions]:
        if container.count > 0:
            conn = container.connectivity
            for old_id, new_id in remap.items():
                conn[conn == old_id] = new_id

    # Remove duplicate nodes
    keep_mask = np.array([int(nid) not in to_remove for nid in mesh_part.nodes.ids])
    mesh_part.nodes.remove_by_mask(keep_mask)

    for key in list(mesh_part.node_data.keys()):
        mesh_part.node_data[key] = mesh_part.node_data[key][keep_mask]

    logger.info(f"Merged {len(to_remove)} duplicate nodes")
    return len(to_remove)


def compute_centroid(mesh_part: MeshPart) -> np.ndarray:
    """Compute the centroid of all nodes.

    Returns:
        (3,) array of (x_center, y_center, z_center).
    """
    if mesh_part.nodes.count == 0:
        return np.zeros(3)
    return mesh_part.nodes.coords.mean(axis=0)


def compute_bounding_box(mesh_part: MeshPart) -> tuple[np.ndarray, np.ndarray]:
    """Compute axis-aligned bounding box.

    Returns:
        (min_coords, max_coords): each a (3,) array.
    """
    if mesh_part.nodes.count == 0:
        return np.zeros(3), np.zeros(3)
    return mesh_part.nodes.coords.min(axis=0), mesh_part.nodes.coords.max(axis=0)
