"""Tests for processing/buildings.py — Fase 3."""

import numpy as np
import pytest

from geodata.core.mesh_part import MeshPart
from geodata.processing.buildings import (
    place_buildings_on_terrain,
    delete_buildings_outside_boundary,
    delete_buildings_under_value,
    compute_distance_from_hull,
    add_distance_from_hull,
    find_building_terrain_distances,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_terrain(z_func=None) -> MeshPart:
    """Create a simple flat terrain (10x10 grid, 2 triangles).

    Optionally apply z_func(x, y) -> z.
    """
    mp = MeshPart(name="Terrain")
    # 4 corner nodes
    coords = np.array([
        [0, 0, 0],
        [10, 0, 0],
        [10, 10, 0],
        [0, 10, 0],
    ], dtype=np.float64)

    if z_func is not None:
        for i in range(len(coords)):
            coords[i, 2] = z_func(coords[i, 0], coords[i, 1])

    ids = np.arange(1, 5, dtype=np.int64)
    mp.create_nodes_bulk(ids, coords)
    mp.create_elements_bulk("tri3", np.array([1, 2], dtype=np.int64),
                            np.array([[1, 2, 3], [1, 3, 4]], dtype=np.int64))
    return mp


def _make_tilted_terrain() -> MeshPart:
    """Terrain with a slope: z = 0.5 * x."""
    return _make_terrain(z_func=lambda x, y: 0.5 * x)


def _make_building(x_offset=3.0, y_offset=3.0, height=5.0, name="Building_1") -> MeshPart:
    """Create a simple box-like building at (x_offset, y_offset).

    Base nodes at z=0, roof nodes at z=height.
    1x1 footprint.
    """
    mp = MeshPart(name="Buildings")

    # Base: 4 nodes at z=0, Roof: 4 nodes at z=height
    base = np.array([
        [x_offset, y_offset, 0],
        [x_offset + 1, y_offset, 0],
        [x_offset + 1, y_offset + 1, 0],
        [x_offset, y_offset + 1, 0],
    ], dtype=np.float64)
    roof = base.copy()
    roof[:, 2] = height

    coords = np.vstack([base, roof])
    ids = np.arange(1, 9, dtype=np.int64)
    mp.create_nodes_bulk(ids, coords)

    # 4 triangles for walls (enough for testing)
    mp.create_elements_bulk("tri3", np.array([1, 2, 3, 4], dtype=np.int64),
                            np.array([
                                [1, 2, 5],  # wall 1
                                [2, 3, 6],  # wall 2
                                [3, 4, 7],  # wall 3
                                [4, 1, 8],  # wall 4
                            ], dtype=np.int64))

    # Create sub-part for the building
    sp = mp.create_sub_part(name)
    for nid in ids:
        c = mp.nodes.get_coords(int(nid))
        sp.nodes.add(int(nid), c[0], c[1], c[2])
    sp.create_elements_bulk("tri3", mp.elements.ids.copy(), mp.elements.connectivity.copy())

    return mp


def _make_two_buildings() -> MeshPart:
    """Create two buildings: one inside terrain, one outside."""
    mp = MeshPart(name="Buildings")

    # Building 1: inside terrain (3,3)
    b1_base = np.array([
        [3, 3, 0], [4, 3, 0], [4, 4, 0], [3, 4, 0],
    ], dtype=np.float64)
    b1_roof = b1_base.copy()
    b1_roof[:, 2] = 5.0

    # Building 2: outside terrain (20,20)
    b2_base = np.array([
        [20, 20, 0], [21, 20, 0], [21, 21, 0], [20, 21, 0],
    ], dtype=np.float64)
    b2_roof = b2_base.copy()
    b2_roof[:, 2] = 5.0

    coords = np.vstack([b1_base, b1_roof, b2_base, b2_roof])
    ids = np.arange(1, 17, dtype=np.int64)
    mp.create_nodes_bulk(ids, coords)

    mp.create_elements_bulk("tri3",
                            np.array([1, 2, 3, 4], dtype=np.int64),
                            np.array([
                                [1, 2, 5], [3, 4, 7],   # building 1 walls
                                [9, 10, 13], [11, 12, 15],  # building 2 walls
                            ], dtype=np.int64))

    # Sub-parts
    sp1 = mp.create_sub_part("Building_1")
    for nid in range(1, 9):
        c = mp.nodes.get_coords(nid)
        sp1.nodes.add(nid, c[0], c[1], c[2])
    sp1.create_elements_bulk("tri3",
                             np.array([1, 2], dtype=np.int64),
                             mp.elements.connectivity[:2].copy())

    sp2 = mp.create_sub_part("Building_2")
    for nid in range(9, 17):
        c = mp.nodes.get_coords(nid)
        sp2.nodes.add(nid, c[0], c[1], c[2])
    sp2.create_elements_bulk("tri3",
                             np.array([3, 4], dtype=np.int64),
                             mp.elements.connectivity[2:].copy())

    return mp


# ---------------------------------------------------------------------------
# Tests: place_buildings_on_terrain
# ---------------------------------------------------------------------------

class TestPlaceBuildingsOnTerrain:

    def test_flat_terrain(self):
        """Buildings on flat terrain (z=0) should not change base Z."""
        terrain = _make_terrain()
        buildings = _make_building(x_offset=3.0, y_offset=3.0, height=5.0)

        removed = place_buildings_on_terrain(buildings, terrain)

        assert removed == []
        sp = buildings.get_sub_part("Building_1")
        # Base nodes should be at z~0 (flat terrain)
        for nid in [1, 2, 3, 4]:
            z = sp.nodes.get_coords(nid)[2]
            assert z == pytest.approx(0.0, abs=0.1)

    def test_tilted_terrain(self):
        """Buildings on tilted terrain should shift to terrain Z."""
        terrain = _make_tilted_terrain()  # z = 0.5 * x
        buildings = _make_building(x_offset=3.0, y_offset=3.0, height=5.0)

        removed = place_buildings_on_terrain(buildings, terrain)

        assert removed == []
        sp = buildings.get_sub_part("Building_1")
        # Base node at x=3: terrain_z = 0.5*3 = 1.5
        base_z = sp.nodes.get_coords(1)[2]
        assert base_z == pytest.approx(1.5, abs=0.2)

        # Roof nodes should be shifted up
        roof_z = sp.nodes.get_coords(5)[2]
        assert roof_z > 5.0  # shifted above original height

    def test_remove_outside(self):
        """Buildings outside terrain should be removed."""
        terrain = _make_terrain()
        buildings = _make_two_buildings()

        removed = place_buildings_on_terrain(buildings, terrain, remove_outside=True)

        assert "Building_2" in removed
        assert buildings.has_sub_part("Building_1")
        assert not buildings.has_sub_part("Building_2")

    def test_keep_outside(self):
        """With remove_outside=False, buildings outside terrain are kept."""
        terrain = _make_terrain()
        buildings = _make_two_buildings()

        removed = place_buildings_on_terrain(buildings, terrain, remove_outside=False)

        assert removed == []
        assert buildings.has_sub_part("Building_2")

    def test_empty_terrain(self):
        """Empty terrain should not crash."""
        terrain = MeshPart(name="Empty")
        buildings = _make_building()

        removed = place_buildings_on_terrain(buildings, terrain)
        assert removed == []


# ---------------------------------------------------------------------------
# Tests: delete_buildings_outside_boundary
# ---------------------------------------------------------------------------

class TestDeleteBuildingsOutsideBoundary:

    def test_inside_circle(self):
        """Building inside circle should be kept."""
        buildings = _make_building(x_offset=3.0, y_offset=3.0)

        removed = delete_buildings_outside_boundary(buildings, 5.0, 5.0, radius=10.0)

        assert removed == []
        assert buildings.has_sub_part("Building_1")

    def test_outside_circle(self):
        """Building outside circle should be removed."""
        buildings = _make_two_buildings()

        removed = delete_buildings_outside_boundary(buildings, 5.0, 5.0, radius=8.0)

        assert "Building_2" in removed
        assert not buildings.has_sub_part("Building_2")
        assert buildings.has_sub_part("Building_1")

    def test_all_inside(self):
        """All buildings inside: nothing removed."""
        buildings = _make_building(x_offset=3.0, y_offset=3.0)

        removed = delete_buildings_outside_boundary(buildings, 3.5, 3.5, radius=100.0)

        assert removed == []

    def test_all_outside(self):
        """All buildings outside: all removed."""
        buildings = _make_building(x_offset=3.0, y_offset=3.0)

        removed = delete_buildings_outside_boundary(buildings, 100.0, 100.0, radius=1.0)

        assert "Building_1" in removed
        assert len(buildings.sub_parts) == 0


# ---------------------------------------------------------------------------
# Tests: delete_buildings_under_value
# ---------------------------------------------------------------------------

class TestDeleteBuildingsUnderValue:

    def test_building_at_z_zero(self):
        """Building with base at z=0 should be removed (z <= threshold)."""
        buildings = _make_building(x_offset=3.0, y_offset=3.0)

        removed = delete_buildings_under_value(buildings, z_value=0.5)

        assert "Building_1" in removed

    def test_shifted_building_kept(self):
        """Building shifted above threshold should be kept."""
        buildings = _make_building(x_offset=3.0, y_offset=3.0, height=5.0)

        # Shift all nodes up
        sp = buildings.get_sub_part("Building_1")
        sp.nodes.coords[:, 2] += 2.0

        removed = delete_buildings_under_value(buildings, z_value=1.0)

        assert removed == []
        assert buildings.has_sub_part("Building_1")


# ---------------------------------------------------------------------------
# Tests: compute_distance_from_hull
# ---------------------------------------------------------------------------

class TestDistanceFromHull:

    def test_basic_distance(self):
        """Distance field should have positive and negative values."""
        # Domain: a box of tet4 would be complex; use a simple set of query points
        domain = MeshPart(name="Domain")
        # Create nodes inside and outside a building
        coords = np.array([
            [3.5, 3.5, 2.5],   # inside building
            [0.0, 0.0, 0.0],   # outside building
            [10.0, 10.0, 10.0],  # far outside
        ], dtype=np.float64)
        domain.create_nodes_bulk(np.arange(1, 4, dtype=np.int64), coords)

        # Building: a closed box (use trimesh to create)
        import trimesh
        box = trimesh.creation.box(extents=[1, 1, 5])
        box.apply_translation([3.5, 3.5, 2.5])
        buildings = MeshPart.from_trimesh(box, name="Buildings", as_elements=True)

        distances = compute_distance_from_hull(domain, buildings)

        assert domain.has_node_field("DISTANCE")
        # Node inside should have negative distance (inside building)
        assert distances[0] < 0
        # Nodes outside should have positive distance
        assert distances[1] > 0
        assert distances[2] > 0

    def test_size_reduction(self):
        """Size reduction should shift the distance field."""
        domain = MeshPart(name="Domain")
        coords = np.array([[3.5, 3.5, 2.5]], dtype=np.float64)
        domain.create_nodes_bulk(np.array([1], dtype=np.int64), coords)

        import trimesh
        box = trimesh.creation.box(extents=[2, 2, 5])
        box.apply_translation([3.5, 3.5, 2.5])
        buildings = MeshPart.from_trimesh(box, name="Buildings", as_elements=True)

        d1 = compute_distance_from_hull(domain, buildings, size_reduction=0.0)
        d2 = compute_distance_from_hull(domain, buildings, size_reduction=1.0)

        # With size_reduction=1.0, distance should be shifted by +1.0
        assert d2[0] == pytest.approx(d1[0] + 1.0, abs=0.01)

    def test_empty_buildings(self):
        """Empty building mesh should return large positive distances."""
        domain = MeshPart(name="Domain")
        domain.create_nodes_bulk(np.array([1], dtype=np.int64),
                                 np.array([[0, 0, 0]], dtype=np.float64))
        buildings = MeshPart(name="Empty")

        distances = compute_distance_from_hull(domain, buildings)
        assert distances[0] > 100.0


# ---------------------------------------------------------------------------
# Tests: add_distance_from_hull
# ---------------------------------------------------------------------------

class TestAddDistanceFromHull:

    def test_accumulate_minimum(self):
        """Adding distances should take the minimum."""
        domain = MeshPart(name="Domain")
        coords = np.array([
            [2.0, 2.0, 2.5],   # near building A, far from B
            [8.0, 8.0, 2.5],   # far from A, near building B
        ], dtype=np.float64)
        domain.create_nodes_bulk(np.arange(1, 3, dtype=np.int64), coords)

        import trimesh

        # Building A at (2, 2, 2.5)
        box_a = trimesh.creation.box(extents=[1, 1, 5])
        box_a.apply_translation([2.0, 2.0, 2.5])
        buildings_a = MeshPart.from_trimesh(box_a, name="A", as_elements=True)

        # Building B at (8, 8, 2.5)
        box_b = trimesh.creation.box(extents=[1, 1, 5])
        box_b.apply_translation([8.0, 8.0, 2.5])
        buildings_b = MeshPart.from_trimesh(box_b, name="B", as_elements=True)

        # First hull
        compute_distance_from_hull(domain, buildings_a)
        d_after_a = domain.get_node_field("DISTANCE").copy()

        # Add second hull (minimum)
        add_distance_from_hull(domain, buildings_b)
        d_after_ab = domain.get_node_field("DISTANCE")

        # Node 1 (near A): distance from A < distance from B, should keep A's value
        assert d_after_ab[0] == pytest.approx(d_after_a[0], abs=0.1)
        # Node 2 (near B): distance from B < distance from A, should use B's value
        assert d_after_ab[1] < d_after_a[1]


# ---------------------------------------------------------------------------
# Tests: find_building_terrain_distances
# ---------------------------------------------------------------------------

class TestFindBuildingTerrainDistances:

    def test_basic(self):
        """Should return base and top coordinates."""
        terrain = _make_tilted_terrain()
        buildings = _make_building(x_offset=3.0, y_offset=3.0, height=5.0)

        base_list, top_list = find_building_terrain_distances(buildings, terrain)

        assert len(base_list) > 0
        assert len(top_list) > 0

        # Base coords should have z > 0 (shifted to terrain)
        for base in base_list:
            assert (base[:, 2] > 0).any()

    def test_empty_terrain(self):
        """Empty terrain should return empty lists."""
        terrain = MeshPart(name="Empty")
        buildings = _make_building()

        base_list, top_list = find_building_terrain_distances(buildings, terrain)

        assert base_list == []
        assert top_list == []
