"""Tests for CFD modules: model, boundary, parameters, and config/defaults."""

import json
import math
import os

import numpy as np
import pytest

from geodata.core.mesh_part import MeshPart


# ===========================================================================
# Helper: create a simple tet4 volume mesh with sub-parts
# ===========================================================================

def _make_volume_mesh() -> MeshPart:
    """Create a simple mesh with volume elements and surface sub-parts."""
    mp = MeshPart(name="TestDomain")

    # 5 nodes forming 2 tetrahedra
    node_ids = np.array([1, 2, 3, 4, 5], dtype=np.int64)
    coords = np.array([
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 1, 1],
    ], dtype=np.float64)
    mp.create_nodes_bulk(node_ids, coords)
    mp.create_elements_bulk("tet4", np.array([1, 2], dtype=np.int64),
                             np.array([[1, 2, 3, 4], [2, 3, 4, 5]], dtype=np.int64))

    # Surface sub-parts (tri3)
    for name, nids, eids, conn in [
        ("TopModelPart", [3, 4, 5], [10], [[3, 4, 5]]),
        ("BottomModelPart", [1, 2, 3], [11], [[1, 2, 3]]),
        ("LateralSector_1", [1, 2, 4], [12], [[1, 2, 4]]),
        ("LateralSector_2", [2, 3, 5], [13], [[2, 3, 5]]),
        ("LateralSector_3", [1, 3, 4], [14], [[1, 3, 4]]),
        ("LateralSector_4", [2, 4, 5], [15], [[2, 4, 5]]),
    ]:
        sp = mp.create_sub_part(name)
        sp_nids = np.array(nids, dtype=np.int64)
        sp_coords = coords[np.array(nids) - 1]
        sp.create_nodes_bulk(sp_nids, sp_coords)
        sp.create_elements_bulk("tri3",
                                 np.array(eids, dtype=np.int64),
                                 np.array(conn, dtype=np.int64))

    return mp


# ===========================================================================
# cfd/model.py tests
# ===========================================================================

class TestCfdModel:
    def test_create_from_mesh(self):
        from geodata.cfd.model import CfdModel

        source = _make_volume_mesh()
        model = CfdModel()
        cfd_mp = model.create_from_mesh(source)

        assert cfd_mp.nodes.count == 5
        assert cfd_mp.elements.count == 2
        assert "TopModelPart" in cfd_mp.sub_parts
        assert "BottomModelPart" in cfd_mp.sub_parts

    def test_fill_parts_fluid(self):
        from geodata.cfd.model import CfdModel

        source = _make_volume_mesh()
        # Add a "Volume" sub-part with the tet4 elements
        vol_sp = source.create_sub_part("Volume")
        vol_sp.create_nodes_bulk(source.nodes.ids.copy(), source.nodes.coords.copy())
        vol_sp.create_elements_bulk("tet4", source.elements.ids.copy(),
                                     source.elements.connectivity.copy())

        model = CfdModel()
        model.create_from_mesh(source)
        model.fill_parts_fluid("Volume")

        assert "Parts_Fluid" in model.mesh_part.sub_parts
        assert "Volume" not in model.mesh_part.sub_parts
        pf = model.mesh_part.get_sub_part("Parts_Fluid")
        assert pf.nodes.count == 5
        assert pf.elements.count == 2

    def test_fill_boundary(self):
        from geodata.cfd.model import CfdModel

        source = _make_volume_mesh()
        model = CfdModel()
        model.create_from_mesh(source)
        model.fill_boundary("Inlet", "LateralSector_1")

        assert "Inlet" in model.mesh_part.sub_parts
        assert "LateralSector_1" not in model.mesh_part.sub_parts

    def test_fill_boundary_invalid_type(self):
        from geodata.cfd.model import CfdModel

        source = _make_volume_mesh()
        model = CfdModel()
        model.create_from_mesh(source)

        with pytest.raises(ValueError, match="boundary_type"):
            model.fill_boundary("InvalidType", "TopModelPart")

    def test_assign_inlet_outlet_sectors(self):
        from geodata.cfd.model import CfdModel

        source = _make_volume_mesh()
        model = CfdModel()
        model.create_from_mesh(source)

        result = model.assign_inlet_outlet_sectors(
            wind_direction=1, n_sectors=4,
            inlet_velocity=10.0,
        )

        assert len(result["inlet_sectors"]) == 2
        assert len(result["outlet_sectors"]) == 2
        assert result["velocity"] == 10.0
        # Wind from East (sector 1), direction should point west (negative x)
        assert result["direction_vector"][0] < 0

    def test_no_model_raises(self):
        from geodata.cfd.model import CfdModel

        model = CfdModel()
        with pytest.raises(RuntimeError):
            model.fill_parts_fluid("anything")


# ===========================================================================
# cfd/boundary.py tests
# ===========================================================================

class TestBoundaryConditions:
    def test_noslip_bc(self):
        from geodata.cfd.boundary import NoSlipBC

        bc = NoSlipBC(sub_part_name="SKIN_ISOSURFACE")
        assert bc.bc_type == "noslip"
        assert bc.sub_part_name == "SKIN_ISOSURFACE"

    def test_inlet_bc_default(self):
        from geodata.cfd.boundary import InletBC

        bc = InletBC(sub_part_name="LateralSector_1")
        assert bc.velocity == 6.0
        assert bc.direction == "automatic_inwards_normal"

    def test_outlet_bc(self):
        from geodata.cfd.boundary import OutletBC

        bc = OutletBC(sub_part_name="LateralSector_7", pressure=0.0)
        assert bc.bc_type == "outlet"
        assert bc.pressure == 0.0

    def test_wind_direction_vector(self):
        from geodata.cfd.boundary import compute_wind_direction_vector

        # Sector 1 = East → wind blows westward (-x)
        d = compute_wind_direction_vector(1, 12)
        assert d[0] == pytest.approx(-1.0, abs=1e-10)
        assert d[1] == pytest.approx(0.0, abs=1e-10)

        # Sector 4 = North → wind blows southward (-y)
        d = compute_wind_direction_vector(4, 12)
        assert d[0] == pytest.approx(0.0, abs=1e-10)
        assert d[1] == pytest.approx(-1.0, abs=1e-10)

    def test_create_boundary_conditions(self):
        from geodata.cfd.boundary import create_boundary_conditions

        bcs = create_boundary_conditions(
            wind_direction=1, n_sectors=12,
            inlet_velocity=10.0,
        )
        # 6 inlet + 6 outlet + 1 top slip + 1 bottom slip + 1 building noslip = 15
        assert len(bcs) == 15

        types = [bc.bc_type for bc in bcs]
        assert types.count("inlet") == 6
        assert types.count("outlet") == 6
        assert types.count("slip") == 2
        assert types.count("noslip") == 1

    def test_create_boundary_conditions_no_buildings(self):
        from geodata.cfd.boundary import create_boundary_conditions

        bcs = create_boundary_conditions(
            wind_direction=1, n_sectors=4,
            building_name=None,
        )
        # 2 inlet + 2 outlet + 2 slip = 6
        assert len(bcs) == 6


# ===========================================================================
# cfd/parameters.py tests
# ===========================================================================

class TestParameters:
    def test_generate_kratos_parameters(self):
        from geodata.cfd.parameters import generate_kratos_parameters

        params = generate_kratos_parameters("test_project")

        assert params["problem_data"]["problem_name"] == "test_project"
        assert params["solver_settings"]["solver_type"] == "Monolithic"
        assert params["solver_settings"]["volume_model_part_name"] == "Parts_Fluid"

    def test_with_boundary_conditions(self):
        from geodata.cfd.boundary import InletBC, NoSlipBC, OutletBC, SlipBC
        from geodata.cfd.parameters import generate_kratos_parameters

        bcs = [
            InletBC(sub_part_name="Inlet", velocity=10.0, direction=[-1, 0, 0]),
            OutletBC(sub_part_name="Outlet"),
            SlipBC(sub_part_name="Top"),
            NoSlipBC(sub_part_name="Buildings"),
        ]
        params = generate_kratos_parameters("with_bcs", boundary_conditions=bcs)

        skin_parts = params["solver_settings"]["skin_parts"]
        assert "Inlet" in skin_parts
        assert "Outlet" in skin_parts
        assert "Top" in skin_parts
        assert "Buildings" in skin_parts

        bc_list = params["processes"]["boundary_conditions_process_list"]
        assert len(bc_list) == 4

        # Check inlet has velocity
        inlet_params = next(p for p in bc_list if p["process_name"] == "ApplyInletProcess")
        assert inlet_params["Parameters"]["modulus"] == 10.0
        assert inlet_params["Parameters"]["direction"] == [-1, 0, 0]

    def test_write_parameters_json(self, tmp_path):
        from geodata.cfd.parameters import generate_kratos_parameters, write_parameters_json

        params = generate_kratos_parameters("test_write")
        out = str(tmp_path / "params.json")
        result = write_parameters_json(params, out)

        assert os.path.exists(result)
        with open(result) as f:
            loaded = json.load(f)
        assert loaded["problem_data"]["problem_name"] == "test_write"

    def test_custom_solver_settings(self):
        from geodata.cfd.parameters import generate_kratos_parameters

        params = generate_kratos_parameters(
            "custom", solver_type="FractionalStep",
            time_step=0.05, end_time=10.0,
        )
        assert params["solver_settings"]["solver_type"] == "FractionalStep"
        assert params["solver_settings"]["time_stepping"]["time_step"] == 0.05
        assert params["problem_data"]["end_time"] == 10.0


# ===========================================================================
# config/defaults.py tests
# ===========================================================================

class TestDefaults:
    def test_default_project(self):
        from geodata.config.defaults import default_project

        settings = default_project("my_project")
        assert settings.project_name == "my_project"
        assert settings.cfd is None
        assert settings.buildings is None

    def test_urban_wind_project(self):
        from geodata.config.defaults import urban_wind_project

        settings = urban_wind_project(
            inlet_velocity=10.0,
            wind_direction=4,
            domain_radius=500.0,
        )
        assert settings.cfd is not None
        assert settings.cfd.enabled is True
        assert settings.cfd.inlet_velocity == 10.0
        assert settings.cfd.wind_direction == 4
        assert settings.domain.radius == 500.0
        assert settings.buildings is not None

    def test_terrain_only_project(self):
        from geodata.config.defaults import terrain_only_project

        settings = terrain_only_project()
        assert settings.buildings is None
        assert settings.cfd is None
        assert settings.output.content == "terrain_only"

    def test_osm_project(self):
        from geodata.config.defaults import osm_project

        settings = osm_project(latitude=42.0, longitude=14.0, radius_m=1000.0)
        assert settings.terrain.source == "dem"
        assert settings.buildings.source == "osm"
        assert settings.cfd.enabled is True

    def test_settings_roundtrip_json(self, tmp_path):
        from geodata.config.defaults import urban_wind_project

        settings = urban_wind_project()
        path = str(tmp_path / "settings.json")
        settings.to_json_file(path)

        from geodata.config.settings import ProjectSettings
        loaded = ProjectSettings.from_json_file(path)
        assert loaded.project_name == settings.project_name
        assert loaded.cfd.inlet_velocity == settings.cfd.inlet_velocity
