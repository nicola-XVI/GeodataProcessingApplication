"""Tests for meshing modules: triangulation, domain, refinement sizes."""

import math
import numpy as np
import pytest

from geodata.core.mesh_part import MeshPart
from geodata.meshing.triangulation import triangulate_2d, triangulate_points_to_mesh_part
from geodata.meshing.domain import create_sectors
from geodata.meshing.refinement import compute_refinement_sizes
from geodata.processing.cleaning import (
    clean_isolated_nodes, clean_invalid_conditions, fill_bottom_sub_part, validate_mesh,
)
from geodata.processing.terrain import smooth_terrain_z, set_extrusion_height


class TestTriangulate2D:
    def test_basic(self):
        pts = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=np.float64)
        verts, tris = triangulate_2d(pts)
        assert len(verts) >= 4
        assert len(tris) >= 2  # At least 2 triangles for a quad

    def test_to_mesh_part(self):
        pts = np.array([[0, 0], [1, 0], [0.5, 1]], dtype=np.float64)
        z = np.array([0, 0, 5.0])
        mp = triangulate_points_to_mesh_part(pts, z_values=z, name="Tri")
        assert mp.nodes.count >= 3
        assert mp.elements.count >= 1
        # Check Z values preserved
        assert mp.nodes.coords[2, 2] == pytest.approx(5.0)


class TestSectors:
    def _make_domain_with_lateral(self) -> MeshPart:
        """Create a simple domain with lateral conditions around a circle."""
        mp = MeshPart(name="Domain")

        # Create nodes around a circle at z=0 and z=10
        n_pts = 12
        r = 100.0
        node_id = 1
        for i in range(n_pts):
            theta = 2 * math.pi * i / n_pts
            x = r * math.cos(theta)
            y = r * math.sin(theta)
            mp.create_node(node_id, x, y, 0.0)
            mp.create_node(node_id + n_pts, x, y, 10.0)
            node_id += 1

        # Create lateral conditions (triangles connecting bottom to top)
        lateral = mp.create_sub_part("LateralModelPart")
        cond_id = 1
        for i in range(n_pts):
            i_next = (i + 1) % n_pts
            b0, b1 = i + 1, i_next + 1
            t0, t1 = i + 1 + n_pts, i_next + 1 + n_pts

            mp.create_condition("tri3", cond_id, [b0, b1, t1])
            lateral.conditions.add(cond_id, [b0, b1, t1])
            for nid in [b0, b1, t1]:
                if not lateral.nodes.has_node(nid):
                    c = mp.nodes.get_coords(nid)
                    lateral.nodes.add(nid, c[0], c[1], c[2])
            cond_id += 1

            mp.create_condition("tri3", cond_id, [b0, t1, t0])
            lateral.conditions.add(cond_id, [b0, t1, t0])
            for nid in [b0, t1, t0]:
                if not lateral.nodes.has_node(nid):
                    c = mp.nodes.get_coords(nid)
                    lateral.nodes.add(nid, c[0], c[1], c[2])
            cond_id += 1

        mp.process_info["X_CENTER"] = 0.0
        mp.process_info["Y_CENTER"] = 0.0
        return mp

    def test_create_sectors(self):
        mp = self._make_domain_with_lateral()
        create_sectors(mp, n_sectors=4)

        # LateralModelPart should be removed
        assert not mp.has_sub_part("LateralModelPart")

        # Should have 4 sector sub-parts
        for i in range(1, 5):
            assert mp.has_sub_part(f"LateralSector_{i}")

        # All conditions should be classified
        total = sum(mp.get_sub_part(f"LateralSector_{i}").conditions.count for i in range(1, 5))
        assert total == 24  # 12 quads * 2 triangles each


class TestRefinementSizes:
    def test_linear(self):
        nodes = np.array([[0, 0, 0], [5, 0, 0], [10, 0, 0]], dtype=np.float64)
        ref = np.array([[0, 0, 0]], dtype=np.float64)
        sizes = compute_refinement_sizes(nodes, ref, min_size=1.0, max_size=10.0,
                                          boundary_layer_distance=10.0, interpolation="linear")
        assert sizes[0] == pytest.approx(1.0)  # At reference
        assert sizes[1] == pytest.approx(5.5)  # Halfway
        assert sizes[2] == pytest.approx(10.0)  # At boundary

    def test_constant(self):
        nodes = np.array([[0, 0, 0], [100, 0, 0]], dtype=np.float64)
        ref = np.array([[0, 0, 0]], dtype=np.float64)
        sizes = compute_refinement_sizes(nodes, ref, min_size=1.0, max_size=50.0,
                                          boundary_layer_distance=5.0, interpolation="constant")
        assert sizes[0] == pytest.approx(1.0)
        assert sizes[1] == pytest.approx(50.0)


class TestCleaning:
    def test_clean_isolated_nodes(self):
        mp = MeshPart()
        mp.create_nodes_bulk(np.array([1, 2, 3, 4], dtype=np.int64), np.zeros((4, 3)))
        mp.create_element("tri3", 1, [1, 2, 3])
        removed = clean_isolated_nodes(mp)
        assert removed == 1  # Node 4 is isolated
        assert mp.nodes.count == 3

    def test_clean_invalid_conditions(self):
        mp = MeshPart()
        mp.create_nodes_bulk(np.array([1, 2, 3], dtype=np.int64), np.zeros((3, 3)))
        mp.create_condition("tri3", 1, [1, 2, 3])
        mp.create_condition("tri3", 2, [1, 2, 99])  # Node 99 doesn't exist
        removed = clean_invalid_conditions(mp)
        assert removed == 1
        assert mp.conditions.count == 1

    def test_fill_bottom(self):
        mp = MeshPart()
        mp.create_nodes_bulk(np.array([1, 2, 3, 4, 5, 6], dtype=np.int64),
                             np.zeros((6, 3)))
        mp.create_condition("tri3", 1, [1, 2, 3])
        mp.create_condition("tri3", 2, [4, 5, 6])

        # Classify only condition 1 into a sub-part
        sp = mp.create_sub_part("TopModelPart")
        sp.conditions.add(1, [1, 2, 3])

        fill_bottom_sub_part(mp)
        assert mp.has_sub_part("BottomModelPart")
        bottom = mp.get_sub_part("BottomModelPart")
        assert bottom.conditions.count == 1  # Condition 2

    def test_validate_mesh(self):
        mp = MeshPart()
        mp.create_nodes_bulk(np.array([1, 2, 3], dtype=np.int64),
                             np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64))
        mp.create_element("tri3", 1, [1, 2, 3])
        result = validate_mesh(mp)
        assert result["valid"]
        assert result["nodes"] == 3
        assert result["elements"] == 1


class TestTerrainProcessing:
    def test_smooth_terrain_z(self):
        mp = MeshPart()
        coords = np.array([
            [0, 0, 0],     # center, within r_ground (z_min reference)
            [20, 0, 10],   # within r_ground, unchanged
            [50, 0, 10],   # between r_ground and r_boundary
            [90, 0, 10],   # near boundary
        ], dtype=np.float64)
        mp.create_nodes_bulk(np.arange(1, 5, dtype=np.int64), coords)

        smooth_terrain_z(mp, x_center=0, y_center=0, r_ground=30, r_boundary=100)

        # Center node (z_min) should be unchanged
        assert mp.nodes.get_coords(1)[2] == pytest.approx(0.0)
        # Node within r_ground should be unchanged
        assert mp.nodes.get_coords(2)[2] == pytest.approx(10.0)
        # Nodes beyond r_ground should be smoothed towards z_min=0
        assert mp.nodes.get_coords(3)[2] < 10.0
        assert mp.nodes.get_coords(4)[2] < mp.nodes.get_coords(3)[2]

    def test_extrusion_height(self):
        mp = MeshPart()
        coords = np.array([
            [0, 0, 0], [1, 0, 0], [0, 1, 0],
            [0.5, 0.5, 100],  # Very high point
        ], dtype=np.float64)
        mp.create_nodes_bulk(np.arange(1, 5, dtype=np.int64), coords)

        removed = set_extrusion_height(mp, radius=2.0, height=10.0,
                                        free_board=1.0, smooth_iterations=0)
        assert removed >= 1  # The high point should be removed
        assert mp.has_node_field("EXTRUSION_HEIGHT")
