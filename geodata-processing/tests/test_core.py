"""Tests for core data structures: NodeContainer, ElementContainer, MeshPart."""

import numpy as np
import pytest

from geodata.core.containers import NodeContainer, ElementContainer
from geodata.core.mesh_part import MeshPart


# ---- NodeContainer ----

class TestNodeContainer:
    def test_add_single(self):
        nc = NodeContainer()
        idx = nc.add(1, 0.0, 1.0, 2.0)
        assert idx == 0
        assert nc.count == 1
        assert nc.has_node(1)
        np.testing.assert_array_equal(nc.get_coords(1), [0.0, 1.0, 2.0])

    def test_add_bulk(self):
        nc = NodeContainer()
        ids = np.array([10, 20, 30], dtype=np.int64)
        coords = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.float64)
        nc.add_bulk(ids, coords)
        assert nc.count == 3
        assert nc.has_node(20)
        np.testing.assert_array_equal(nc.get_coords(20), [4, 5, 6])

    def test_duplicate_id_raises(self):
        nc = NodeContainer()
        nc.add(1, 0, 0, 0)
        with pytest.raises(ValueError, match="already exists"):
            nc.add(1, 1, 1, 1)

    def test_remove_by_mask(self):
        nc = NodeContainer()
        nc.add_bulk(np.array([1, 2, 3]), np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]]))
        nc.remove_by_mask(np.array([True, False, True]))
        assert nc.count == 2
        assert nc.has_node(1)
        assert not nc.has_node(2)
        assert nc.has_node(3)

    def test_remove_by_ids(self):
        nc = NodeContainer()
        nc.add_bulk(np.array([1, 2, 3]), np.zeros((3, 3)))
        nc.remove_by_ids({2})
        assert nc.count == 2
        assert not nc.has_node(2)

    def test_iter(self):
        nc = NodeContainer()
        nc.add(5, 1.0, 2.0, 3.0)
        items = list(nc)
        assert items == [(5, 1.0, 2.0, 3.0)]

    def test_max_id(self):
        nc = NodeContainer()
        assert nc.max_id() == 0
        nc.add_bulk(np.array([5, 10, 3]), np.zeros((3, 3)))
        assert nc.max_id() == 10


# ---- ElementContainer ----

class TestElementContainer:
    def test_add_single_tri(self):
        ec = ElementContainer("tri3")
        idx = ec.add(1, [10, 20, 30])
        assert idx == 0
        assert ec.count == 1
        np.testing.assert_array_equal(ec.get_node_ids(1), [10, 20, 30])

    def test_add_bulk(self):
        ec = ElementContainer("tet4")
        ids = np.array([1, 2])
        conn = np.array([[1, 2, 3, 4], [5, 6, 7, 8]])
        ec.add_bulk(ids, conn)
        assert ec.count == 2
        assert ec.has_element(2)

    def test_wrong_node_count_raises(self):
        ec = ElementContainer("tri3")
        with pytest.raises(ValueError, match="Expected 3"):
            ec.add(1, [1, 2, 3, 4])

    def test_get_all_node_ids(self):
        ec = ElementContainer("tri3")
        ec.add_bulk(np.array([1, 2]), np.array([[1, 2, 3], [2, 3, 4]]))
        unique = ec.get_all_node_ids()
        np.testing.assert_array_equal(unique, [1, 2, 3, 4])

    def test_remove_by_mask(self):
        ec = ElementContainer("tri3")
        ec.add_bulk(np.array([1, 2, 3]), np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]]))
        ec.remove_by_mask(np.array([True, False, True]))
        assert ec.count == 2
        assert ec.has_element(1)
        assert not ec.has_element(2)


# ---- MeshPart ----

class TestMeshPart:
    def _make_simple_mesh(self) -> MeshPart:
        """Create a simple triangle mesh for testing."""
        mp = MeshPart(name="Test")
        ids = np.array([1, 2, 3, 4], dtype=np.int64)
        coords = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]
        ], dtype=np.float64)
        mp.create_nodes_bulk(ids, coords)
        mp.create_element("tri3", 1, [1, 2, 3])
        mp.create_element("tri3", 2, [2, 4, 3])
        return mp

    def test_create_nodes_and_elements(self):
        mp = self._make_simple_mesh()
        assert mp.number_of_nodes == 4
        assert mp.number_of_elements == 2

    def test_node_fields(self):
        mp = self._make_simple_mesh()
        field = mp.add_node_field("distance")
        assert field.shape == (4,)
        field[0] = 1.5
        assert mp.get_node_field("distance")[0] == 1.5
        assert mp.has_node_field("distance")

    def test_sub_parts(self):
        mp = self._make_simple_mesh()
        sub = mp.create_sub_part("Ground")
        assert mp.has_sub_part("Ground")
        assert sub.name == "Ground"
        mp.add_nodes_to_sub_part("Ground", [1, 2])
        assert sub.nodes.count == 2

    def test_sub_part_duplicate_raises(self):
        mp = MeshPart()
        mp.create_sub_part("A")
        with pytest.raises(ValueError, match="already exists"):
            mp.create_sub_part("A")

    def test_remove_nodes_by_flag(self):
        mp = self._make_simple_mesh()
        mp.add_node_field("to_remove")
        mp.node_data["to_remove"][3] = 1.0  # Mark node 4
        removed = mp.remove_nodes_by_flag("to_remove")
        assert removed == 1
        assert mp.number_of_nodes == 3
        # Element 2 (uses node 4) should be removed
        assert mp.number_of_elements == 1

    def test_to_trimesh_and_back(self):
        mp = self._make_simple_mesh()
        tm = mp.to_trimesh()
        assert len(tm.vertices) == 4
        assert len(tm.faces) == 2

        mp2 = MeshPart.from_trimesh(tm, name="Roundtrip")
        assert mp2.number_of_nodes == 4
        assert mp2.number_of_elements == 2

    def test_clear(self):
        mp = self._make_simple_mesh()
        mp.clear()
        assert mp.number_of_nodes == 0
        assert mp.number_of_elements == 0

    def test_properties(self):
        mp = MeshPart()
        props = mp.get_properties(0)
        assert isinstance(props, dict)
        props["viscosity"] = 0.001
        assert mp.get_properties(0)["viscosity"] == 0.001
