"""Tests for spatial utilities and field computations."""

import numpy as np
import pytest

from geodata.core.spatial import (
    SpatialTree, PointLocator,
    compute_extrusion_height, smooth_extrusion_height,
)
from geodata.core.fields import (
    compute_triangle_normals, compute_vertex_normals,
    compute_nodal_gradient_tri3, compute_distance_field_from_points,
)


class TestSpatialTree:
    def test_query_radius(self):
        coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [10, 10, 0]], dtype=np.float64)
        tree = SpatialTree(coords)
        neighbors = tree.query_radius(np.array([0, 0, 0]), 1.5)
        assert set(neighbors) == {0, 1, 2}

    def test_query_radius_2d(self):
        coords = np.array([[0, 0, 0], [1, 0, 100], [0, 1, 200]], dtype=np.float64)
        tree = SpatialTree(coords, use_2d=True)
        neighbors = tree.query_radius(np.array([0, 0, 0]), 1.5)
        # Should find all 3 since Z is ignored in 2D
        assert set(neighbors) == {0, 1, 2}

    def test_query_nearest(self):
        coords = np.array([[0, 0, 0], [1, 0, 0], [5, 5, 5]], dtype=np.float64)
        tree = SpatialTree(coords)
        dists, idxs = tree.query_nearest(np.array([0.1, 0, 0]), k=1)
        assert idxs[0] == 0

    def test_query_nearest_batch(self):
        coords = np.array([[0, 0, 0], [10, 10, 10]], dtype=np.float64)
        tree = SpatialTree(coords)
        pts = np.array([[0, 0, 0], [10, 10, 10]])
        dists, idxs = tree.query_nearest_batch(pts, k=1)
        assert idxs[0, 0] == 0
        assert idxs[1, 0] == 1


class TestPointLocator:
    def test_find_simplex_2d(self):
        # Unit square with 4 corners, triangulated
        points = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
        locator = PointLocator(points, use_2d=True)

        # Point inside should find a simplex
        inside = locator.find_simplex(np.array([[0.5, 0.5, 0]]))
        assert inside[0] >= 0

        # Point outside should return -1
        outside = locator.find_simplex(np.array([[5.0, 5.0, 0]]))
        assert outside[0] == -1

    def test_is_inside(self):
        points = np.array([[0, 0, 0], [1, 0, 0], [0.5, 1, 0]], dtype=np.float64)
        locator = PointLocator(points, use_2d=True)
        result = locator.is_inside(np.array([[0.4, 0.3, 0], [5, 5, 0]]))
        assert result[0] == True
        assert result[1] == False


class TestExtrusionHeight:
    def test_basic(self):
        # Flat terrain at z=0, one elevated point
        coords = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0.5, 0.5, 50]
        ], dtype=np.float64)
        heights, keep = compute_extrusion_height(coords, radius=2.0, max_height=10.0, free_board=0.0)
        # The elevated point (z=50) should be marked for removal since 50 > 0 + 10
        assert not keep[4]
        # Ground points should be kept
        assert all(keep[:4])

    def test_smooth(self):
        coords = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=np.float64)
        heights = np.array([10.0, 20.0, 10.0])
        smoothed = smooth_extrusion_height(coords, heights, radius=1.5, iterations=1)
        # Middle point should be smoothed toward neighbors
        assert smoothed[1] < 20.0


class TestTriangleNormals:
    def test_flat_triangle(self):
        coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
        conn = np.array([[0, 1, 2]])
        normals = compute_triangle_normals(coords, conn)
        # Normal should point in Z direction
        np.testing.assert_allclose(normals[0], [0, 0, 1], atol=1e-10)

    def test_vertex_normals(self):
        # Two triangles sharing an edge, both in XY plane
        coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64)
        conn = np.array([[0, 1, 2], [1, 3, 2]])
        normals = compute_vertex_normals(coords, conn)
        # All vertex normals should point in Z direction
        for i in range(4):
            np.testing.assert_allclose(abs(normals[i, 2]), 1.0, atol=1e-10)


class TestGradient:
    def test_linear_field(self):
        # Triangle with linear scalar field f(x,y) = x
        coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)
        conn = np.array([[0, 1, 2]])
        scalar = np.array([0.0, 1.0, 0.0])
        grad = compute_nodal_gradient_tri3(coords, conn, scalar)
        # Gradient should be approximately (1, 0, 0)
        for i in range(3):
            np.testing.assert_allclose(grad[i, 0], 1.0, atol=1e-10)
            np.testing.assert_allclose(grad[i, 1], 0.0, atol=1e-10)


class TestDistanceField:
    def test_basic(self):
        ref = np.array([[0, 0, 0], [10, 10, 10]], dtype=np.float64)
        query = np.array([[0, 0, 0], [1, 0, 0], [10, 10, 10]], dtype=np.float64)
        dists = compute_distance_field_from_points(query, ref)
        assert dists[0] == pytest.approx(0.0)
        assert dists[2] == pytest.approx(0.0)
        assert dists[1] > 0
