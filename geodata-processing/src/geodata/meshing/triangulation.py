"""2D Delaunay triangulation wrapper using the triangle library.

Provides constrained and unconstrained 2D triangulation for surface meshing.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def triangulate_2d(
    points: np.ndarray,
    segments: Optional[np.ndarray] = None,
    holes: Optional[np.ndarray] = None,
    max_area: Optional[float] = None,
    min_angle: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Perform 2D Delaunay triangulation.

    Args:
        points: (N, 2) array of 2D coordinates.
        segments: (S, 2) array of constrained edge segments (0-based indices).
        holes: (H, 2) array of hole seed points.
        max_area: Maximum triangle area constraint.
        min_angle: Minimum angle constraint in degrees.

    Returns:
        (vertices, triangles): vertices is (M, 2), triangles is (T, 3) 0-based.
    """
    import triangle as tr

    tri_input = dict(vertices=np.asarray(points, dtype=np.float64).tolist())

    if segments is not None and len(segments) > 0:
        tri_input["segments"] = np.asarray(segments, dtype=np.int32).tolist()

    if holes is not None and len(holes) > 0:
        tri_input["holes"] = np.asarray(holes, dtype=np.float64).tolist()

    # Build options string
    opts = ""
    if segments is not None:
        opts += "p"  # PSLG mode
    if max_area is not None:
        opts += f"a{max_area}"
    if min_angle > 0:
        opts += f"q{min_angle}"

    tri_result = tr.triangulate(tri_input, opts) if opts else tr.triangulate(tri_input)

    vertices = np.array(tri_result["vertices"], dtype=np.float64)
    triangles = np.array(tri_result["triangles"], dtype=np.int64)

    return vertices, triangles


def triangulate_points_to_mesh_part(
    points_2d: np.ndarray,
    z_values: Optional[np.ndarray] = None,
    name: str = "Triangulation",
    max_area: Optional[float] = None,
) -> MeshPart:
    """Triangulate 2D points and create a MeshPart with the result.

    Args:
        points_2d: (N, 2) array of XY coordinates.
        z_values: (N,) array of Z values. If None, Z=0.
        name: Name for the resulting MeshPart.
        max_area: Maximum triangle area constraint.

    Returns:
        MeshPart with triangulated surface mesh.
    """
    vertices, triangles = triangulate_2d(points_2d, max_area=max_area)

    n_verts = len(vertices)
    if z_values is not None and len(z_values) >= n_verts:
        z = z_values[:n_verts]
    elif z_values is not None:
        # Triangle may add Steiner points; interpolate Z for them
        z = np.zeros(n_verts)
        z[:len(z_values)] = z_values
        # Simple nearest-neighbor for new points
        if n_verts > len(z_values):
            from scipy.spatial import cKDTree
            tree = cKDTree(points_2d[:len(z_values)])
            _, idx = tree.query(vertices[len(z_values):])
            z[len(z_values):] = z_values[idx]
    else:
        z = np.zeros(n_verts)

    mp = MeshPart(name=name)
    node_ids = np.arange(1, n_verts + 1, dtype=np.int64)
    coords_3d = np.column_stack([vertices, z])
    mp.create_nodes_bulk(node_ids, coords_3d)

    n_tri = len(triangles)
    if n_tri > 0:
        elem_ids = np.arange(1, n_tri + 1, dtype=np.int64)
        elem_conn = triangles + 1  # to 1-based
        mp.create_elements_bulk("tri3", elem_ids, elem_conn)

    logger.info(f"Triangulated: {n_verts} vertices, {n_tri} triangles")
    return mp


def triangulate_with_boundary(
    interior_points: np.ndarray,
    boundary_points: np.ndarray,
    interior_z: Optional[np.ndarray] = None,
    boundary_z: Optional[np.ndarray] = None,
    name: str = "Triangulation",
) -> MeshPart:
    """Triangulate interior points with a constrained boundary polygon.

    Args:
        interior_points: (N, 2) interior XY coordinates.
        boundary_points: (M, 2) boundary XY coordinates (ordered CCW).
        interior_z: (N,) Z values for interior points.
        boundary_z: (M,) Z values for boundary points.
        name: Name for the MeshPart.

    Returns:
        MeshPart with constrained triangulation.
    """
    import triangle as tr

    n_int = len(interior_points)
    n_bnd = len(boundary_points)

    all_pts = np.vstack([interior_points, boundary_points])

    # Build boundary segments (closed polygon)
    segments = np.zeros((n_bnd, 2), dtype=np.int32)
    for i in range(n_bnd):
        segments[i] = [n_int + i, n_int + (i + 1) % n_bnd]

    tri_input = dict(
        vertices=all_pts.tolist(),
        segments=segments.tolist(),
    )
    tri_result = tr.triangulate(tri_input, "p")

    vertices = np.array(tri_result["vertices"], dtype=np.float64)
    triangles = np.array(tri_result["triangles"], dtype=np.int64)

    # Build Z values
    n_verts = len(vertices)
    z = np.zeros(n_verts)
    if interior_z is not None:
        z[:min(n_int, n_verts)] = interior_z[:min(n_int, n_verts)]
    if boundary_z is not None:
        for i in range(min(n_bnd, n_verts - n_int)):
            if n_int + i < n_verts:
                z[n_int + i] = boundary_z[i]

    mp = MeshPart(name=name)
    node_ids = np.arange(1, n_verts + 1, dtype=np.int64)
    coords_3d = np.column_stack([vertices, z])
    mp.create_nodes_bulk(node_ids, coords_3d)

    if len(triangles) > 0:
        elem_ids = np.arange(1, len(triangles) + 1, dtype=np.int64)
        mp.create_elements_bulk("tri3", elem_ids, triangles + 1)

    logger.info(f"Constrained triangulation: {n_verts} vertices, {len(triangles)} triangles")
    return mp
