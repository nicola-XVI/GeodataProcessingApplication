"""Field computation utilities replacing Kratos C++ processes.

Computes distance fields, nodal gradients, and surface normals using
numpy/scipy/trimesh, replacing Kratos ComputeNodalGradientProcess3D,
NormalCalculationUtils, and variational distance computation.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def compute_distance_field_from_surface(
    query_points: np.ndarray,
    surface_vertices: np.ndarray,
    surface_faces: np.ndarray,
    signed: bool = True,
) -> np.ndarray:
    """Compute distance field from a triangulated surface.

    Replaces Kratos VariationalDistanceCalculationProcess + trimesh.proximity.

    Args:
        query_points: (N, 3) points where distance is computed.
        surface_vertices: (V, 3) vertices of the surface mesh.
        surface_faces: (F, 3) face connectivity (0-based indices).
        signed: If True, compute signed distance (negative inside).

    Returns:
        (N,) array of distance values.
    """
    import trimesh

    mesh = trimesh.Trimesh(vertices=surface_vertices, faces=surface_faces)

    if signed:
        # trimesh signed distance: negative inside, positive outside
        distances = trimesh.proximity.signed_distance(mesh, query_points)
    else:
        closest, dist, _ = trimesh.proximity.closest_point(mesh, query_points)
        distances = dist

    return distances


def compute_distance_field_from_points(
    query_points: np.ndarray,
    reference_points: np.ndarray,
    use_2d: bool = False,
) -> np.ndarray:
    """Compute minimum distance from query points to a set of reference points.

    Useful for distance-from-ground or distance-from-buildings computations.

    Args:
        query_points: (N, 3) points where distance is computed.
        reference_points: (M, 3) reference point set.
        use_2d: If True, compute distance using only (x, y).

    Returns:
        (N,) array of minimum distances.
    """
    from scipy.spatial import cKDTree

    if use_2d:
        tree = cKDTree(reference_points[:, :2])
        distances, _ = tree.query(query_points[:, :2])
    else:
        tree = cKDTree(reference_points)
        distances, _ = tree.query(query_points)

    return distances


def compute_nodal_gradient_tet4(
    node_coords: np.ndarray,
    connectivity: np.ndarray,
    scalar_field: np.ndarray,
) -> np.ndarray:
    """Compute nodal gradient of a scalar field on a tetrahedral mesh.

    Replaces Kratos ComputeNodalGradientProcess3D. Uses volume-weighted
    averaging of element gradients to nodes.

    Args:
        node_coords: (N, 3) array of node coordinates.
        connectivity: (M, 4) array of tetrahedral connectivity (0-based indices).
        scalar_field: (N,) array of scalar values at nodes.

    Returns:
        (N, 3) array of gradient vectors at each node.
    """
    n_nodes = len(node_coords)
    n_elems = len(connectivity)

    gradient = np.zeros((n_nodes, 3), dtype=np.float64)
    weight = np.zeros(n_nodes, dtype=np.float64)

    for e in range(n_elems):
        n0, n1, n2, n3 = connectivity[e]
        p0, p1, p2, p3 = node_coords[n0], node_coords[n1], node_coords[n2], node_coords[n3]

        # Jacobian matrix: edges from node 0
        J = np.array([p1 - p0, p2 - p0, p3 - p0]).T  # (3, 3)
        det_J = np.linalg.det(J)

        if abs(det_J) < 1e-20:
            continue

        vol = abs(det_J) / 6.0

        # Shape function gradients for linear tetrahedron
        # dN/dx = J^{-T} * dN/d(xi)
        # For linear tet: dN/d(xi) = [[-1,-1,-1],[1,0,0],[0,1,0],[0,0,1]]
        J_inv_T = np.linalg.inv(J).T
        dN_dxi = np.array([[-1, -1, -1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
        dN_dx = dN_dxi @ J_inv_T  # (4, 3)

        # Element scalar values
        vals = scalar_field[[n0, n1, n2, n3]]

        # Element gradient: sum of (value * shape_function_gradient)
        elem_grad = vals @ dN_dx  # (3,)

        # Distribute to nodes weighted by volume
        for ni in [n0, n1, n2, n3]:
            gradient[ni] += elem_grad * vol
            weight[ni] += vol

    # Average
    mask = weight > 0
    gradient[mask] /= weight[mask, np.newaxis]

    return gradient


def compute_nodal_gradient_tri3(
    node_coords: np.ndarray,
    connectivity: np.ndarray,
    scalar_field: np.ndarray,
) -> np.ndarray:
    """Compute nodal gradient of a scalar field on a triangular surface mesh.

    Args:
        node_coords: (N, 3) array of node coordinates.
        connectivity: (M, 3) array of triangle connectivity (0-based indices).
        scalar_field: (N,) array of scalar values at nodes.

    Returns:
        (N, 3) array of gradient vectors at each node.
    """
    n_nodes = len(node_coords)
    gradient = np.zeros((n_nodes, 3), dtype=np.float64)
    weight = np.zeros(n_nodes, dtype=np.float64)

    for e in range(len(connectivity)):
        n0, n1, n2 = connectivity[e]
        p0, p1, p2 = node_coords[n0], node_coords[n1], node_coords[n2]

        # Edge vectors
        e1 = p1 - p0
        e2 = p2 - p0
        normal = np.cross(e1, e2)
        area2 = np.linalg.norm(normal)

        if area2 < 1e-20:
            continue

        area = area2 / 2.0
        n_hat = normal / area2

        # Gradient in the plane of the triangle
        vals = scalar_field[[n0, n1, n2]]
        # Using the formula: grad(f) = (1/(2*area)) * sum(f_i * (n x e_opposite_i))
        grad = (
            vals[0] * np.cross(n_hat, p2 - p1)
            + vals[1] * np.cross(n_hat, p0 - p2)
            + vals[2] * np.cross(n_hat, p1 - p0)
        ) / (2.0 * area)

        for ni in [n0, n1, n2]:
            gradient[ni] += grad * area
            weight[ni] += area

    mask = weight > 0
    gradient[mask] /= weight[mask, np.newaxis]
    return gradient


def compute_triangle_normals(
    node_coords: np.ndarray,
    connectivity: np.ndarray,
    normalize: bool = True,
) -> np.ndarray:
    """Compute face normals for triangular elements.

    Args:
        node_coords: (N, 3) node coordinates.
        connectivity: (M, 3) triangle connectivity (0-based indices).
        normalize: If True, return unit normals.

    Returns:
        (M, 3) array of face normal vectors.
    """
    p0 = node_coords[connectivity[:, 0]]
    p1 = node_coords[connectivity[:, 1]]
    p2 = node_coords[connectivity[:, 2]]

    normals = np.cross(p1 - p0, p2 - p0)

    if normalize:
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths = np.maximum(lengths, 1e-20)  # avoid division by zero
        normals = normals / lengths

    return normals


def compute_vertex_normals(
    node_coords: np.ndarray,
    connectivity: np.ndarray,
) -> np.ndarray:
    """Compute per-vertex normals by area-weighted averaging of face normals.

    Replaces Kratos NormalCalculationUtils.

    Args:
        node_coords: (N, 3) node coordinates.
        connectivity: (M, 3) triangle connectivity (0-based indices).

    Returns:
        (N, 3) array of vertex normal vectors (unit length).
    """
    n_nodes = len(node_coords)
    vertex_normals = np.zeros((n_nodes, 3), dtype=np.float64)

    # Compute face normals (unnormalized = area-weighted)
    face_normals = compute_triangle_normals(node_coords, connectivity, normalize=False)

    # Accumulate to vertices
    for i in range(3):
        np.add.at(vertex_normals, connectivity[:, i], face_normals)

    # Normalize
    lengths = np.linalg.norm(vertex_normals, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-20)
    vertex_normals /= lengths

    return vertex_normals
