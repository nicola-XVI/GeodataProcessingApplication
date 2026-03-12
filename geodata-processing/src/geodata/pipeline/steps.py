"""Pipeline step definitions (Strategy pattern).

Each step is a callable that takes a PipelineContext and modifies it
in-place. Steps can be composed in any order via the PipelineRunner.

Port of the workflow in test_application.py, decomposed into reusable steps.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..config.settings import ProjectSettings
from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Shared state passed between pipeline steps.

    Each step reads and modifies this context.
    """
    settings: ProjectSettings
    output_dir: str = "output"

    # Mesh data populated by steps
    terrain: Optional[MeshPart] = None
    buildings: Optional[MeshPart] = None
    domain: Optional[MeshPart] = None      # volume mesh after domain creation
    final_mesh: Optional[MeshPart] = None  # final mesh after all processing

    # Metadata
    step_log: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def log_step(self, name: str, message: str = "") -> None:
        entry = f"[{name}] {message}" if message else f"[{name}] done"
        self.step_log.append(entry)
        logger.info(entry)


class PipelineStep:
    """Base class for pipeline steps."""

    name: str = "base_step"

    def run(self, ctx: PipelineContext) -> None:
        raise NotImplementedError

    def __call__(self, ctx: PipelineContext) -> None:
        return self.run(ctx)


class LoadTerrainStep(PipelineStep):
    """Load terrain from file.

    Reads STL, OBJ, XYZ, or DEM terrain files.
    """
    name = "load_terrain"

    def run(self, ctx: PipelineContext) -> None:
        settings = ctx.settings.terrain
        if not settings.file_path:
            ctx.errors.append("No terrain file path specified")
            return

        from ..io.readers import read_stl, read_obj

        ext = os.path.splitext(settings.file_path)[1].lower()

        if ext == ".stl":
            ctx.terrain = read_stl(settings.file_path)
        elif ext == ".obj":
            ctx.terrain = read_obj(settings.file_path)
        else:
            # Try generic reader via meshio
            from ..io.readers import read_mesh
            ctx.terrain = read_mesh(settings.file_path)

        if ctx.terrain is None or ctx.terrain.nodes.count == 0:
            ctx.errors.append(f"Failed to load terrain from {settings.file_path}")
            return

        ctx.log_step(self.name, f"{ctx.terrain.nodes.count} nodes loaded")


class PreprocessTerrainStep(PipelineStep):
    """Preprocess terrain: shift, filter height, cut to domain."""
    name = "preprocess_terrain"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.terrain is None:
            return

        from ..processing.preprocessor import shift_to_center, filter_by_height

        settings = ctx.settings.terrain

        if settings.shift_to_origin:
            shift_to_center(ctx.terrain)

        if settings.min_height_filter is not None:
            filter_by_height(ctx.terrain, min_z=settings.min_height_filter)

        if settings.max_height_filter is not None:
            filter_by_height(ctx.terrain, max_z=settings.max_height_filter)

        ctx.log_step(self.name, f"{ctx.terrain.nodes.count} nodes after preprocessing")


class CreateDomainStep(PipelineStep):
    """Create cylindrical computational domain with terrain."""
    name = "create_domain"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.terrain is None:
            ctx.errors.append("No terrain loaded, cannot create domain")
            return

        from ..meshing.domain import create_cylindrical_domain

        ds = ctx.settings.domain
        ctx.domain = create_cylindrical_domain(
            terrain=ctx.terrain,
            radius=ds.radius,
            height=ds.height,
            n_divisions=ds.circular_divisions,
            n_sectors=ds.num_sectors,
        )

        ctx.log_step(self.name, f"{ctx.domain.nodes.count} nodes, "
                     f"{ctx.domain.elements.count} elements")


class LoadBuildingsStep(PipelineStep):
    """Load building geometry from file."""
    name = "load_buildings"

    def run(self, ctx: PipelineContext) -> None:
        bs = ctx.settings.buildings
        if bs is None or not bs.file_path:
            ctx.log_step(self.name, "skipped (no buildings configured)")
            return

        from ..io.readers import read_obj

        ext = os.path.splitext(bs.file_path)[1].lower()
        if ext == ".obj":
            ctx.buildings = read_obj(bs.file_path, extract_groups=True)
        else:
            from ..io.readers import read_mesh
            ctx.buildings = read_mesh(bs.file_path)

        if ctx.buildings and bs.change_coordinates:
            # Swap Y and Z for OSM2World OBJ files
            from ..processing.preprocessor import swap_yz_coordinates
            swap_yz_coordinates(ctx.buildings)

        if ctx.buildings:
            ctx.log_step(self.name, f"{ctx.buildings.nodes.count} nodes, "
                         f"{len(ctx.buildings.sub_parts)} sub-parts")
        else:
            ctx.errors.append(f"Failed to load buildings from {bs.file_path}")


class PlaceBuildingsStep(PipelineStep):
    """Place buildings on terrain surface."""
    name = "place_buildings"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.buildings is None or ctx.terrain is None:
            ctx.log_step(self.name, "skipped (no buildings or terrain)")
            return

        bs = ctx.settings.buildings
        if bs is None or not bs.shift_on_terrain:
            ctx.log_step(self.name, "skipped (shift_on_terrain=False)")
            return

        from ..processing.buildings import place_buildings_on_terrain

        removed = place_buildings_on_terrain(ctx.buildings, ctx.terrain)
        ctx.log_step(self.name, f"placed, {len(removed)} removed as outside terrain")


class SubtractBuildingsStep(PipelineStep):
    """Subtract building volumes from domain mesh."""
    name = "subtract_buildings"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.domain is None or ctx.buildings is None:
            ctx.log_step(self.name, "skipped (no domain or buildings)")
            return

        from ..processing.buildings import compute_distance_from_hull

        # Compute distance field from building hull
        compute_distance_from_hull(ctx.domain, ctx.buildings)

        # Boolean subtraction via trimesh
        from ..meshing.boolean_ops import subtract_buildings

        ctx.domain = subtract_buildings(ctx.domain, ctx.buildings)
        ctx.log_step(self.name, f"{ctx.domain.nodes.count} nodes after subtraction")


class RefineMeshStep(PipelineStep):
    """Refine mesh near ground and buildings."""
    name = "refine_mesh"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.domain is None:
            return

        ms = ctx.settings.mesh

        from ..meshing.refinement import refine_with_distance_field

        ctx.domain = refine_with_distance_field(
            ctx.domain,
            min_size=ms.min_element_size,
            max_size=ms.max_element_size,
        )
        ctx.log_step(self.name, f"{ctx.domain.nodes.count} nodes, "
                     f"{ctx.domain.elements.count} elements after refinement")


class CleanMeshStep(PipelineStep):
    """Clean mesh: remove isolated nodes, invalid conditions."""
    name = "clean_mesh"

    def run(self, ctx: PipelineContext) -> None:
        if ctx.domain is None:
            return

        from ..processing.cleaning import clean_isolated_nodes, validate_mesh

        n_removed = clean_isolated_nodes(ctx.domain)
        report = validate_mesh(ctx.domain)

        ctx.log_step(self.name, f"removed {n_removed} isolated nodes, "
                     f"valid={report.get('is_valid', True)}")


class SetupCfdStep(PipelineStep):
    """Set up CFD boundary conditions and generate parameter files."""
    name = "setup_cfd"

    def run(self, ctx: PipelineContext) -> None:
        cfd = ctx.settings.cfd
        if cfd is None or not cfd.enabled:
            ctx.log_step(self.name, "skipped (CFD not enabled)")
            return

        if ctx.domain is None:
            ctx.errors.append("No domain mesh for CFD setup")
            return

        from ..cfd.boundary import create_boundary_conditions
        from ..cfd.parameters import generate_kratos_parameters, write_parameters_json

        bcs = create_boundary_conditions(
            wind_direction=cfd.wind_direction,
            n_sectors=ctx.settings.domain.num_sectors,
            inlet_velocity=cfd.inlet_velocity,
        )

        params = generate_kratos_parameters(
            problem_name=ctx.settings.project_name,
            boundary_conditions=bcs,
            solver_type=cfd.solver_type,
            time_step=cfd.time_step,
            end_time=cfd.end_time,
        )

        if cfd.generate_json:
            json_path = os.path.join(ctx.output_dir, "ProjectParameters.json")
            write_parameters_json(params, json_path)
            ctx.log_step(self.name, f"wrote {json_path}")
        else:
            ctx.log_step(self.name, "parameters generated (not written)")


class ExportStep(PipelineStep):
    """Export final mesh to configured output formats."""
    name = "export"

    def run(self, ctx: PipelineContext) -> None:
        mesh = ctx.domain or ctx.terrain
        if mesh is None:
            ctx.errors.append("No mesh to export")
            return

        ctx.final_mesh = mesh

        from ..io.writers import write_auto

        os.makedirs(ctx.output_dir, exist_ok=True)
        output = ctx.settings.output

        for fmt in output.formats:
            out_path = os.path.join(ctx.output_dir,
                                     f"{ctx.settings.project_name}.{fmt}")

            if fmt in ("step", "iges"):
                from ..io.cad_export import is_available
                if not is_available():
                    logger.warning(f"cadquery not available, skipping {fmt} export")
                    continue
                from ..io.cad_export import export_mesh_part
                export_mesh_part(mesh, out_path, fmt=fmt)
            else:
                write_auto(mesh, out_path)

            ctx.log_step(self.name, f"exported {out_path}")
