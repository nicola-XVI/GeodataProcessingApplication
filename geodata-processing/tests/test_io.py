"""Tests for I/O readers and writers."""

import tempfile
import os

import numpy as np
import pytest

from geodata.core.mesh_part import MeshPart
from geodata.io.writers import write_obj, write_xyz, write_auto
from geodata.io.readers import read_obj, read_xyz


def _make_triangle_mesh() -> MeshPart:
    """Create a minimal triangle mesh."""
    mp = MeshPart(name="TestMesh")
    mp.create_nodes_bulk(
        np.array([1, 2, 3], dtype=np.int64),
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
    )
    mp.create_element("tri3", 1, [1, 2, 3])
    return mp


class TestObjRoundtrip:
    def test_write_read_obj(self, tmp_path):
        mp = _make_triangle_mesh()
        obj_path = str(tmp_path / "test.obj")
        write_obj(mp, obj_path)

        mp2 = read_obj(obj_path, extract_groups=False)
        assert mp2.nodes.count == 3
        assert mp2.elements.count == 1

    def test_obj_with_subparts(self, tmp_path):
        mp = _make_triangle_mesh()
        sub = mp.create_sub_part("Building_1")
        sub.nodes.add(1, 0, 0, 0)
        sub.nodes.add(2, 1, 0, 0)
        sub.nodes.add(3, 0, 1, 0)
        sub.create_element("tri3", 1, [1, 2, 3])

        obj_path = str(tmp_path / "groups.obj")
        write_obj(mp, obj_path, include_sub_parts=True)

        mp2 = read_obj(obj_path, extract_groups=True)
        assert mp2.nodes.count == 3
        assert len(mp2.sub_parts) >= 1


class TestXyzRoundtrip:
    def test_write_read_xyz(self, tmp_path):
        mp = MeshPart(name="Points")
        mp.create_nodes_bulk(
            np.array([1, 2, 3], dtype=np.int64),
            np.array([[1.5, 2.5, 3.5], [4.5, 5.5, 6.5], [7.5, 8.5, 9.5]], dtype=np.float64),
        )
        xyz_path = str(tmp_path / "test.xyz")
        write_xyz(mp, xyz_path)

        mp2 = read_xyz(xyz_path)
        assert mp2.nodes.count == 3
        # Check coordinates preserved
        np.testing.assert_allclose(mp2.nodes.coords[0], [1.5, 2.5, 3.5])


class TestWriteAuto:
    def test_unsupported_format_raises(self, tmp_path):
        mp = _make_triangle_mesh()
        with pytest.raises(ValueError, match="Unsupported"):
            write_auto(mp, str(tmp_path / "test.foo"))
