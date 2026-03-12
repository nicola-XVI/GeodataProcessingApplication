"""CFD model assembly.

Port of GeoModel + FillCfdModelpartUtilities: creates a CFD-ready MeshPart
with boundary condition sub-parts (Parts_Fluid, Inlet, Outlet, Slip, NoSlip).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)

# Default fluid properties
DEFAULT_DENSITY = 1.0          # kg/m³ (air)
DEFAULT_DYNAMIC_VISCOSITY = 0.002  # Pa·s (approximate for air ~18e-6, kept as legacy default)


class CfdModel:
    """CFD model builder: assembles volume mesh with boundary sub-parts.

    Port of GeoModel class. Replaces Kratos-based CFD model part creation
    and FillCfdModelpartUtilities C++ class.

    The model organizes a volume mesh (tet4 elements) with named boundary
    surface sub-parts:
    - Parts_Fluid: volume elements (tet4)
    - Inlet: inlet boundary surface (tri3 conditions)
    - Outlet: outlet boundary surface (tri3 conditions)
    - Slip: free-slip wall boundary (tri3 conditions)
    - NoSlip: no-slip wall boundary (tri3 conditions)
    """

    def __init__(self, name: str = "CFD_model_part"):
        self.name = name
        self.mesh_part: Optional[MeshPart] = None
        self.properties = {
            "DENSITY": DEFAULT_DENSITY,
            "DYNAMIC_VISCOSITY": DEFAULT_DYNAMIC_VISCOSITY,
        }

    def create_from_mesh(self, source: MeshPart) -> MeshPart:
        """Create a CFD model part from an existing volume mesh.

        Port of GeoModel.GenerateCfdModelPart + FillCfdModelpartUtilities.FillModelPart.

        Copies all nodes and elements from source, then organizes boundary
        sub-parts based on source's existing sub-parts.

        Args:
            source: Source MeshPart with volume elements and boundary sub-parts.

        Returns:
            New MeshPart organized for CFD analysis.
        """
        self.mesh_part = MeshPart(name=self.name)

        # Copy all nodes and elements from source
        if source.nodes.count > 0:
            self.mesh_part.create_nodes_bulk(source.nodes.ids.copy(),
                                              source.nodes.coords.copy())

        if source.elements.count > 0:
            self.mesh_part.create_elements_bulk(
                source.elements.element_type,
                source.elements.ids.copy(),
                source.elements.connectivity.copy(),
            )

        # Copy sub-parts from source
        for sp_name, sp in source.sub_parts.items():
            new_sp = self.mesh_part.create_sub_part(sp_name)
            if sp.nodes.count > 0:
                new_sp.create_nodes_bulk(sp.nodes.ids.copy(), sp.nodes.coords.copy())
            if sp.elements.count > 0:
                new_sp.create_elements_bulk(
                    sp.elements.element_type,
                    sp.elements.ids.copy(),
                    sp.elements.connectivity.copy(),
                )

        logger.info(f"Created CFD model: {self.mesh_part.nodes.count} nodes, "
                    f"{self.mesh_part.elements.count} elements, "
                    f"{len(self.mesh_part.sub_parts)} sub-parts")
        return self.mesh_part

    def fill_parts_fluid(self, volume_sub_part_name: str) -> None:
        """Designate a sub-part as the fluid volume (Parts_Fluid).

        Port of FillCfdModelpartUtilities::FillPartsFluid.
        Moves nodes and elements from the named sub-part into Parts_Fluid.

        Args:
            volume_sub_part_name: Name of the sub-part containing volume elements.
        """
        if self.mesh_part is None:
            raise RuntimeError("CFD model not created. Call create_from_mesh first.")

        source_sp = self.mesh_part.get_sub_part(volume_sub_part_name)
        if source_sp is None:
            raise ValueError(f"Sub-part '{volume_sub_part_name}' not found")

        if "Parts_Fluid" not in self.mesh_part.sub_parts:
            fluid_sp = self.mesh_part.create_sub_part("Parts_Fluid")
        else:
            fluid_sp = self.mesh_part.get_sub_part("Parts_Fluid")

        # Copy nodes and elements
        if source_sp.nodes.count > 0:
            fluid_sp.create_nodes_bulk(source_sp.nodes.ids.copy(),
                                        source_sp.nodes.coords.copy())
        if source_sp.elements.count > 0:
            fluid_sp.create_elements_bulk(
                source_sp.elements.element_type,
                source_sp.elements.ids.copy(),
                source_sp.elements.connectivity.copy(),
            )

        # Remove original sub-part
        self.mesh_part.remove_sub_part(volume_sub_part_name)

        logger.info(f"Filled Parts_Fluid: {fluid_sp.nodes.count} nodes, "
                    f"{fluid_sp.elements.count} elements")

    def fill_boundary(
        self,
        boundary_type: str,
        source_sub_part_name: str,
        remove_source: bool = True,
    ) -> None:
        """Move a surface sub-part into a boundary condition sub-part.

        Port of FillCfdModelpartUtilities::FillInlet/FillOutlet/FillSlip/FillNoslip.

        Args:
            boundary_type: One of "Inlet", "Outlet", "Slip", "NoSlip".
            source_sub_part_name: Name of the source sub-part.
            remove_source: If True, remove the source sub-part after copying.
        """
        valid_types = ("Inlet", "Outlet", "Slip", "NoSlip")
        if boundary_type not in valid_types:
            raise ValueError(f"boundary_type must be one of {valid_types}")

        if self.mesh_part is None:
            raise RuntimeError("CFD model not created. Call create_from_mesh first.")

        source_sp = self.mesh_part.get_sub_part(source_sub_part_name)
        if source_sp is None:
            raise ValueError(f"Sub-part '{source_sub_part_name}' not found")

        if boundary_type not in self.mesh_part.sub_parts:
            bc_sp = self.mesh_part.create_sub_part(boundary_type)
        else:
            bc_sp = self.mesh_part.get_sub_part(boundary_type)

        # Merge nodes and elements into boundary sub-part
        if source_sp.nodes.count > 0:
            _merge_into_sub_part(bc_sp, source_sp)

        if remove_source:
            self.mesh_part.remove_sub_part(source_sub_part_name)

        logger.info(f"Filled {boundary_type} from '{source_sub_part_name}': "
                    f"{bc_sp.nodes.count} nodes, {bc_sp.elements.count} elements")

    def assign_inlet_outlet_sectors(
        self,
        wind_direction: int,
        n_sectors: int = 12,
        inlet_velocity: float = 6.0,
        sector_base_name: str = "LateralSector_",
    ) -> dict:
        """Assign inlet and outlet boundary conditions to lateral sectors.

        Port of GeoModel.Inlet_Outlet. Determines which lateral sectors
        are inlet (upwind half) and which are outlet (downwind half)
        based on wind direction.

        Wind direction convention (for 12 sectors):
            1 = East, 4 = North, 7 = West, 10 = South

        Args:
            wind_direction: Incoming wind direction sector number (1-based).
            n_sectors: Total number of lateral sectors.
            inlet_velocity: Inlet velocity magnitude in m/s.
            sector_base_name: Base name for sector sub-parts.

        Returns:
            Dict with keys "inlet_sectors", "outlet_sectors", "direction_vector",
            describing the assignment.
        """
        if wind_direction < 1 or wind_direction > n_sectors:
            raise ValueError(f"wind_direction must be 1..{n_sectors}, got {wind_direction}")

        half = n_sectors // 2
        quarter = n_sectors // 4

        # Wind direction angle (counterclockwise from +X)
        theta = (360.0 / n_sectors) * (wind_direction - 1)
        dir_x = -math.cos(math.radians(theta))  # negative = incoming
        dir_y = -math.sin(math.radians(theta))
        direction = [dir_x, dir_y, 0.0]

        # Inlet sectors: half-circle centered on wind direction
        inlet_start = wind_direction - quarter
        inlet_sectors = []
        for i in range(half):
            s = inlet_start + i
            if s <= 0:
                s += n_sectors
            elif s > n_sectors:
                s -= n_sectors
            inlet_sectors.append(s)

        # Outlet sectors: opposite half-circle
        outlet_start = wind_direction + half - quarter
        outlet_sectors = []
        for i in range(half):
            s = outlet_start + i
            if s <= 0:
                s += n_sectors
            elif s > n_sectors:
                s -= n_sectors
            outlet_sectors.append(s)

        # Fill boundary sub-parts
        if self.mesh_part is not None:
            for s in inlet_sectors:
                sp_name = f"{sector_base_name}{s}"
                if sp_name in self.mesh_part.sub_parts:
                    self.fill_boundary("Inlet", sp_name)

            for s in outlet_sectors:
                sp_name = f"{sector_base_name}{s}"
                if sp_name in self.mesh_part.sub_parts:
                    self.fill_boundary("Outlet", sp_name)

        result = {
            "inlet_sectors": inlet_sectors,
            "outlet_sectors": outlet_sectors,
            "direction_vector": direction,
            "velocity": inlet_velocity,
            "angle_deg": theta,
        }

        logger.info(f"Wind dir={wind_direction}: inlet sectors={inlet_sectors}, "
                    f"outlet sectors={outlet_sectors}, "
                    f"direction=({dir_x:.3f}, {dir_y:.3f})")
        return result


def _merge_into_sub_part(target: MeshPart, source: MeshPart) -> None:
    """Merge source nodes/elements into target, avoiding duplicates."""
    if source.nodes.count == 0:
        return

    # Find new nodes not already in target
    if target.nodes.count == 0:
        target.create_nodes_bulk(source.nodes.ids.copy(), source.nodes.coords.copy())
        if source.elements.count > 0:
            target.create_elements_bulk(
                source.elements.element_type,
                source.elements.ids.copy(),
                source.elements.connectivity.copy(),
            )
        return

    existing_ids = set(target.nodes.ids.tolist())
    new_mask = np.array([int(nid) not in existing_ids for nid in source.nodes.ids])

    if new_mask.any():
        new_ids = source.nodes.ids[new_mask]
        new_coords = source.nodes.coords[new_mask]
        # Add new nodes one by one (since create_nodes_bulk expects empty container)
        for nid, coord in zip(new_ids, new_coords):
            target.nodes.add(int(nid), float(coord[0]), float(coord[1]), float(coord[2]))

    if source.elements.count > 0:
        existing_eids = set(target.elements.ids.tolist()) if target.elements.count > 0 else set()
        for i in range(source.elements.count):
            eid = int(source.elements.ids[i])
            if eid not in existing_eids:
                target.elements.add(eid, source.elements.connectivity[i])
