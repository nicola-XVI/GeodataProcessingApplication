"""Default configuration presets for common use cases.

Provides factory functions that create pre-configured ProjectSettings
for typical CFD urban wind simulation scenarios.
"""

from __future__ import annotations

from .settings import (
    BuildingSettings,
    CfdSettings,
    DomainSettings,
    MeshSettings,
    OutputSettings,
    ProjectSettings,
    TerrainSettings,
)


def default_project(name: str = "geodata_project") -> ProjectSettings:
    """Create a default project configuration.

    Suitable for a basic terrain-only simulation without buildings or CFD.
    """
    return ProjectSettings(project_name=name)


def urban_wind_project(
    name: str = "urban_wind",
    terrain_file: str = "",
    building_file: str = "",
    inlet_velocity: float = 6.0,
    wind_direction: int = 1,
    domain_radius: float = 1000.0,
    domain_height: float = 200.0,
) -> ProjectSettings:
    """Create a project configured for urban wind CFD simulation.

    This is the most common use case: terrain + buildings with
    wind boundary conditions.

    Args:
        name: Project name.
        terrain_file: Path to terrain mesh file.
        building_file: Path to building mesh file.
        inlet_velocity: Wind speed at inlet (m/s).
        wind_direction: Wind direction sector (1=East, 4=North, etc.).
        domain_radius: Computational domain radius (m).
        domain_height: Domain height above terrain (m).

    Returns:
        Configured ProjectSettings.
    """
    return ProjectSettings(
        project_name=name,
        domain=DomainSettings(
            radius=domain_radius,
            height=domain_height,
            num_sectors=12,
        ),
        terrain=TerrainSettings(
            source="stl",
            file_path=terrain_file,
            shift_to_origin=True,
        ),
        buildings=BuildingSettings(
            source="obj",
            file_path=building_file,
            shift_on_terrain=True,
        ),
        mesh=MeshSettings(
            min_element_size=1.0,
            max_element_size=50.0,
            near_ground_refinement=True,
            near_building_refinement=True,
        ),
        output=OutputSettings(
            formats=["obj", "vtk"],
            content="air_volume",
        ),
        cfd=CfdSettings(
            enabled=True,
            inlet_velocity=inlet_velocity,
            wind_direction=wind_direction,
            generate_json=True,
        ),
    )


def terrain_only_project(
    name: str = "terrain_only",
    terrain_file: str = "",
    domain_radius: float = 500.0,
) -> ProjectSettings:
    """Create a project for terrain-only mesh generation (no buildings, no CFD)."""
    return ProjectSettings(
        project_name=name,
        domain=DomainSettings(radius=domain_radius),
        terrain=TerrainSettings(
            source="stl",
            file_path=terrain_file,
            shift_to_origin=True,
        ),
        buildings=None,
        mesh=MeshSettings(
            min_element_size=5.0,
            max_element_size=100.0,
        ),
        output=OutputSettings(
            formats=["obj"],
            content="terrain_only",
        ),
        cfd=None,
    )


def osm_project(
    name: str = "osm_project",
    latitude: float = 0.0,
    longitude: float = 0.0,
    radius_m: float = 500.0,
    inlet_velocity: float = 6.0,
    wind_direction: int = 1,
) -> ProjectSettings:
    """Create a project that uses OpenStreetMap and ASTER GDEM data.

    Downloads terrain and building data from online sources.

    Args:
        name: Project name.
        latitude: Center latitude.
        longitude: Center longitude.
        radius_m: Search radius in meters.
        inlet_velocity: Wind speed at inlet (m/s).
        wind_direction: Wind direction sector.

    Returns:
        Configured ProjectSettings.
    """
    return ProjectSettings(
        project_name=name,
        domain=DomainSettings(
            center=(0.0, 0.0),
            radius=radius_m,
            height=max(100.0, radius_m * 0.2),
        ),
        terrain=TerrainSettings(
            source="dem",
            file_path="",
        ),
        buildings=BuildingSettings(
            source="osm",
            file_path="",
        ),
        mesh=MeshSettings(
            min_element_size=max(1.0, radius_m / 500),
            max_element_size=max(10.0, radius_m / 20),
        ),
        output=OutputSettings(
            formats=["obj", "vtk"],
            content="air_volume",
        ),
        cfd=CfdSettings(
            enabled=True,
            inlet_velocity=inlet_velocity,
            wind_direction=wind_direction,
            generate_json=True,
        ),
    )
