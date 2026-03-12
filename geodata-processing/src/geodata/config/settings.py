"""Pydantic-based configuration models for the geodata processing pipeline.

These replace Kratos.Parameters with validated, UI-friendly settings.
JSON schema auto-generation via ProjectSettings.model_json_schema().
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class DomainSettings(BaseModel):
    """Settings for the computational domain."""
    center: tuple[float, float] = (0.0, 0.0)
    radius: float = Field(1000.0, gt=0, description="Radius of cylindrical domain in meters")
    height: float = Field(200.0, gt=0, description="Height above terrain in meters")
    circular_divisions: int = Field(60, ge=8, description="Number of divisions on circular boundary")
    num_sectors: int = Field(12, ge=4, description="Number of wind direction sectors")
    ground_radius_ratio: float = Field(0.667, ge=0.1, le=1.0,
                                        description="Ratio r_ground/r_boundary for terrain smoothing")
    building_radius_ratio: float = Field(0.333, ge=0.0, le=1.0,
                                          description="Ratio r_buildings/r_boundary")


class TerrainSettings(BaseModel):
    """Settings for terrain data input."""
    source: Literal["xyz", "stl", "obj", "dem"] = "stl"
    file_path: str = ""
    shift_to_origin: bool = Field(True, description="Shift terrain center to (0,0)")
    min_height_filter: Optional[float] = Field(None, description="Filter out points below this height")
    max_height_filter: Optional[float] = Field(None, description="Filter out points above this height")


class BuildingSettings(BaseModel):
    """Settings for building data."""
    source: Literal["obj", "osm", "stl"] = "obj"
    file_path: Optional[str] = None
    change_coordinates: bool = Field(False, description="Convert Y=-Z, Z=Y (for OSM2World OBJ files)")
    default_height: float = Field(9.0, gt=0, description="Default building height if not specified")
    height_per_level: float = Field(3.0, gt=0, description="Height per building level in meters")
    shift_on_terrain: bool = Field(True, description="Shift buildings vertically onto terrain surface")


class MeshSettings(BaseModel):
    """Settings for mesh generation and refinement."""
    min_element_size: float = Field(1.0, gt=0, description="Minimum element size in meters")
    max_element_size: float = Field(50.0, gt=0, description="Maximum element size in meters")
    near_ground_refinement: bool = Field(True, description="Enable adaptive refinement near ground")
    near_building_refinement: bool = Field(True, description="Enable refinement near buildings")
    boundary_layer_distance: float = Field(2.0, gt=0,
                                            description="Max distance for boundary layer refinement")
    refinement_interpolation: Literal["linear", "exponential", "constant"] = "linear"


class OutputSettings(BaseModel):
    """Settings for output generation."""
    formats: list[Literal["stl", "obj", "gltf", "glb", "vtk", "step", "iges"]] = ["obj"]
    content: Literal["terrain_only", "buildings_only", "terrain_buildings", "air_volume"] = "air_volume"
    surface_mesh: bool = Field(True, description="Export surface mesh")
    volume_mesh: bool = Field(True, description="Export volumetric mesh (tetrahedra)")
    output_directory: str = Field("output", description="Output directory path")


class CfdSettings(BaseModel):
    """Settings for CFD boundary conditions (optional layer)."""
    enabled: bool = False
    inlet_velocity: float = Field(6.0, gt=0, description="Inlet velocity in m/s")
    wind_direction: int = Field(1, ge=1, description="Wind direction sector number")
    solver_type: Literal["Monolithic", "FractionalStep"] = "Monolithic"
    time_step: float = Field(0.1, gt=0)
    end_time: float = Field(1.0, gt=0)
    generate_json: bool = Field(True, description="Generate solver JSON parameter file")


class ProjectSettings(BaseModel):
    """Root settings for the entire geodata processing pipeline."""
    project_name: str = "geodata_project"
    domain: DomainSettings = DomainSettings()
    terrain: TerrainSettings = TerrainSettings()
    buildings: Optional[BuildingSettings] = None
    mesh: MeshSettings = MeshSettings()
    output: OutputSettings = OutputSettings()
    cfd: Optional[CfdSettings] = None

    @classmethod
    def from_json_file(cls, path: str) -> ProjectSettings:
        """Load settings from a JSON file."""
        import json
        with open(path, "r") as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_json_file(self, path: str) -> None:
        """Save settings to a JSON file."""
        import json
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)
