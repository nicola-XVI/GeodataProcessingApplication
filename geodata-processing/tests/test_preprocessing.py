"""Tests for preprocessing and import utilities."""

import numpy as np
import pytest

from geodata.core.mesh_part import MeshPart
from geodata.processing.preprocessor import (
    cut_by_bounding_box, shift, shift_to_center,
    filter_by_height, swap_yz_coordinates, compute_centroid, compute_bounding_box,
)
from geodata.processing.importer import delete_degenerate_elements


def _make_point_cloud() -> MeshPart:
    mp = MeshPart(name="Cloud")
    coords = np.array([
        [0, 0, 0], [5, 5, 10], [10, 10, 20], [-5, -5, -10], [100, 100, 50]
    ], dtype=np.float64)
    mp.create_nodes_bulk(np.arange(1, 6, dtype=np.int64), coords)
    return mp


class TestCut:
    def test_bounding_box(self):
        mp = _make_point_cloud()
        removed = cut_by_bounding_box(mp, x_min=-1, y_min=-1, x_max=11, y_max=11)
        assert removed == 2  # nodes at (-5,-5) and (100,100)
        assert mp.nodes.count == 3

    def test_shift_to_origin(self):
        mp = _make_point_cloud()
        cut_by_bounding_box(mp, x_min=0, y_min=0, x_max=10, y_max=10, shift_to_origin=True)
        # After shift, min x should be ~0
        assert mp.nodes.coords[:, 0].min() >= -0.01


class TestShift:
    def test_basic(self):
        mp = MeshPart()
        mp.create_node(1, 1.0, 2.0, 3.0)
        shift(mp, 10, 20, 30)
        np.testing.assert_allclose(mp.nodes.get_coords(1), [11, 22, 33])

    def test_shift_to_center(self):
        mp = MeshPart()
        mp.create_nodes_bulk(
            np.array([1, 2], dtype=np.int64),
            np.array([[0, 0, 0], [10, 20, 30]], dtype=np.float64),
        )
        cx, cy = shift_to_center(mp)
        assert cx == pytest.approx(5.0)
        assert cy == pytest.approx(10.0)
        assert mp.nodes.coords[:, 0].mean() == pytest.approx(0.0)


class TestHeightFilter:
    def test_max_height(self):
        mp = _make_point_cloud()
        removed = filter_by_height(mp, max_height=15)
        assert removed == 2  # z=20 and z=50 removed
        assert mp.nodes.count == 3

    def test_min_height(self):
        mp = _make_point_cloud()
        removed = filter_by_height(mp, min_height=0)
        assert removed == 1  # z=-10 removed


class TestSwapYZ:
    def test_swap(self):
        mp = MeshPart()
        mp.create_node(1, 1.0, 2.0, 3.0)
        swap_yz_coordinates(mp)
        coords = mp.nodes.get_coords(1)
        assert coords[1] == pytest.approx(-3.0)
        assert coords[2] == pytest.approx(2.0)


class TestDegenerateElements:
    def test_remove(self):
        mp = MeshPart()
        mp.create_nodes_bulk(np.array([1, 2, 3], dtype=np.int64), np.zeros((3, 3)))
        mp.create_element("tri3", 1, [1, 2, 3])  # valid
        mp.create_element("tri3", 2, [1, 1, 3])  # degenerate
        removed = delete_degenerate_elements(mp)
        assert removed == 1
        assert mp.number_of_elements == 1


class TestBoundingBox:
    def test_compute(self):
        mp = _make_point_cloud()
        mn, mx = compute_bounding_box(mp)
        assert mn[0] == pytest.approx(-5)
        assert mx[0] == pytest.approx(100)


class TestCentroid:
    def test_compute(self):
        mp = MeshPart()
        mp.create_nodes_bulk(
            np.array([1, 2], dtype=np.int64),
            np.array([[0, 0, 0], [10, 10, 10]], dtype=np.float64),
        )
        c = compute_centroid(mp)
        np.testing.assert_allclose(c, [5, 5, 5])
