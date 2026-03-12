"""Spatial search utilities replacing Kratos C++ utilities.

Uses scipy.spatial for O(N log N) neighbor search and point-in-element tests,
replacing the O(N²) brute-force C++ approach with OpenMP.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree, Delaunay

logger = logging.getLogger(__name__)


class SpatialTree:
    """KD-tree wrapper for fast spatial queries on mesh nodes.

    Replaces ExtrusionHeightUtilities' O(N²) brute-force neighbor search.
    """

    def __init__(self, coords: np.ndarray, use_2d: bool = False):
        """Build a KD-tree from coordinates.

        Args:
            coords: (N, 3) array of node coordinates.
            use_2d: If True, build tree using only (x, y) for 2D queries.
        """
        self._coords_3d = np.asarray(coords, dtype=np.float64)
        self._use_2d = use_2d
        tree_coords = self._coords_3d[:, :2] if use_2d else self._coords_3d
        self._tree = cKDTree(tree_coords)

    @property
    def coords(self) -> np.ndarray:
        return self._coords_3d

    def query_radius(self, point: np.ndarray, radius: float) -> np.ndarray:
        """Find all points within radius of a query point.

        Returns array of indices into the original coords array.
        """
        q = np.asarray(point, dtype=np.float64)
        if self._use_2d:
            q = q[:2]
        return np.array(self._tree.query_ball_point(q, radius), dtype=np.intp)

    def query_radius_batch(self, points: np.ndarray, radius: float) -> list[np.ndarray]:
        """Find all points within radius for multiple query points."""
        pts = np.asarray(points, dtype=np.float64)
        if self._use_2d:
            pts = pts[:, :2]
        results = self._tree.query_ball_point(pts, radius)
        return [np.array(r, dtype=np.intp) for r in results]

    def query_nearest(self, point: np.ndarray, k: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """Find k nearest neighbors.

        Returns (distances, indices).
        """
        q = np.asarray(point, dtype=np.float64)
        if self._use_2d:
            q = q[:2]
        distances, indices = self._tree.query(q, k=k)
        return np.atleast_1d(distances), np.atleast_1d(indices)

    def query_nearest_batch(self, points: np.ndarray, k: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """Find k nearest neighbors for multiple query points."""
        pts = np.asarray(points, dtype=np.float64)
        if self._use_2d:
            pts = pts[:, :2]
        distances, indices = self._tree.query(pts, k=k)
        if k == 1:
            distances = distances.reshape(-1, 1)
            indices = indices.reshape(-1, 1)
        return distances, indices


class PointLocator:
    """Point-in-element locator using Delaunay triangulation.

    Replaces Kratos BinBasedFastPointLocator for determining which element
    contains a given point.
    """

    def __init__(self, points: np.ndarray, use_2d: bool = True):
        """Build a Delaunay triangulation for point location.

        Args:
            points: (N, 3) or (N, 2) array of vertex coordinates.
            use_2d: If True, use only (x, y) for 2D triangulation.
        """
        self._points = np.asarray(points, dtype=np.float64)
        if use_2d and self._points.shape[1] == 3:
            self._tri = Delaunay(self._points[:, :2])
        else:
            self._tri = Delaunay(self._points)

    def find_simplex(self, query_points: np.ndarray) -> np.ndarray:
        """Find which simplex (triangle/tetrahedron) contains each query point.

        Returns array of simplex indices (-1 if not found).
        """
        pts = np.asarray(query_points, dtype=np.float64)
        if self._tri.ndim == 2 and pts.shape[-1] == 3:
            pts = pts[..., :2]
        return self._tri.find_simplex(pts)

    def is_inside(self, query_points: np.ndarray) -> np.ndarray:
        """Check if query points are inside the triangulation.

        Returns boolean array.
        """
        return self.find_simplex(query_points) >= 0

    @property
    def simplices(self) -> np.ndarray:
        """Return the simplices (connectivity) of the triangulation."""
        return self._tri.simplices


def compute_extrusion_height(
    node_coords: np.ndarray,
    radius: float,
    max_height: float,
    free_board: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute extrusion height for each node based on nearby minimum Z.

    Replaces ExtrusionHeightUtilities::SetExtrusionHeight (O(N²) → O(N log N)).

    Args:
        node_coords: (N, 3) array of node coordinates.
        radius: Search radius for finding neighbors (2D distance).
        max_height: Height offset above local minimum Z.
        free_board: Buffer zone for node removal threshold.

    Returns:
        (extrusion_heights, keep_mask):
            extrusion_heights: (N,) array of computed extrusion heights.
            keep_mask: (N,) boolean array, True for nodes to keep.
    """
    n = len(node_coords)
    coords = np.asarray(node_coords, dtype=np.float64)

    # Build 2D KD-tree (search by x, y only)
    tree = SpatialTree(coords, use_2d=True)

    extrusion_heights = np.zeros(n, dtype=np.float64)
    keep_mask = np.ones(n, dtype=bool)

    # For each node, find neighbors within radius and compute min Z
    neighbors_list = tree.query_radius_batch(coords, radius)
    for i in range(n):
        neighbors = neighbors_list[i]
        if len(neighbors) == 0:
            extrusion_heights[i] = coords[i, 2] + max_height
            continue

        min_z = coords[neighbors, 2].min()
        target_height = min_z + max_height
        extrusion_heights[i] = target_height

        # Mark for removal if node is above threshold
        if coords[i, 2] > target_height - free_board:
            keep_mask[i] = False

    return extrusion_heights, keep_mask


def smooth_extrusion_height(
    node_coords: np.ndarray,
    extrusion_heights: np.ndarray,
    radius: float,
    iterations: int = 1,
    free_board: float = 0.0,
) -> np.ndarray:
    """Smooth extrusion heights by iterative neighbor averaging.

    Replaces ExtrusionHeightUtilities::SmoothExtrusionHeight.

    Args:
        node_coords: (N, 3) array of node coordinates.
        extrusion_heights: (N,) array of current extrusion heights.
        radius: Search radius for neighbors.
        iterations: Number of smoothing passes.
        free_board: Minimum height threshold above node Z.

    Returns:
        Smoothed extrusion heights array.
    """
    coords = np.asarray(node_coords, dtype=np.float64)
    heights = extrusion_heights.copy()

    tree = SpatialTree(coords, use_2d=True)
    neighbors_list = tree.query_radius_batch(coords, radius)

    for _ in range(iterations):
        new_heights = heights.copy()
        for i in range(len(coords)):
            neighbors = neighbors_list[i]
            if len(neighbors) <= 1:
                continue
            avg_height = heights[neighbors].mean()
            if avg_height > coords[i, 2] + free_board:
                new_heights[i] = 0.5 * heights[i] + 0.5 * avg_height
        heights = new_heights

    return heights
