"""CFD boundary condition definitions.

Port of GeoModel boundary condition parameter generation:
NoSlip, Slip, Inlet, Outlet process configurations.

These are solver-agnostic data structures describing boundary conditions.
The actual JSON parameter generation is in parameters.py.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class NoSlipBC:
    """No-slip wall boundary condition.

    Port of GeoModel.NoSlip. Applied to building surfaces, terrain,
    and bottom boundaries where velocity is zero.
    """
    sub_part_name: str
    bc_type: Literal["noslip"] = "noslip"


@dataclass
class SlipBC:
    """Free-slip wall boundary condition.

    Port of GeoModel.Slip. Applied to top boundary and terrain
    far from buildings where tangential flow is allowed.
    """
    sub_part_name: str
    bc_type: Literal["slip"] = "slip"


@dataclass
class InletBC:
    """Velocity inlet boundary condition.

    Port of GeoModel.Inlet. Applied to upwind lateral sectors.

    Attributes:
        sub_part_name: Name of the boundary sub-part.
        velocity: Inlet velocity magnitude in m/s.
        direction: Wind direction vector [dx, dy, dz] or "automatic_inwards_normal".
        interval: Time interval [start, end] for the BC.
    """
    sub_part_name: str
    velocity: float = 6.0
    direction: Union[list[float], str] = "automatic_inwards_normal"
    interval: list = field(default_factory=lambda: [0.0, "End"])
    bc_type: Literal["inlet"] = "inlet"


@dataclass
class OutletBC:
    """Pressure outlet boundary condition.

    Port of GeoModel.Outlet. Applied to downwind lateral sectors.

    Attributes:
        sub_part_name: Name of the boundary sub-part.
        pressure: Outlet pressure value (typically 0.0 for gauge pressure).
        hydrostatic: Whether to use hydrostatic outlet.
    """
    sub_part_name: str
    pressure: float = 0.0
    hydrostatic: bool = False
    h_top: float = 0.0
    bc_type: Literal["outlet"] = "outlet"


BoundaryCondition = Union[NoSlipBC, SlipBC, InletBC, OutletBC]


def compute_wind_direction_vector(
    wind_sector: int,
    n_sectors: int = 12,
) -> list[float]:
    """Compute the wind direction unit vector from a sector number.

    Convention (12 sectors): 1=East, 4=North, 7=West, 10=South.
    The returned vector points in the incoming wind direction
    (i.e., the direction the wind blows toward).

    Args:
        wind_sector: Sector number (1-based).
        n_sectors: Total number of sectors.

    Returns:
        [dx, dy, dz] unit direction vector.
    """
    theta = (360.0 / n_sectors) * (wind_sector - 1)
    # Negative because wind blows *from* this direction
    dx = -math.cos(math.radians(theta))
    dy = -math.sin(math.radians(theta))
    return [dx, dy, 0.0]


def create_boundary_conditions(
    wind_direction: int,
    n_sectors: int = 12,
    inlet_velocity: float = 6.0,
    sector_base_name: str = "LateralSector_",
    top_name: str = "TopModelPart",
    bottom_name: str = "BottomModelPart",
    building_name: Optional[str] = "SKIN_ISOSURFACE",
) -> list[BoundaryCondition]:
    """Create a complete set of boundary conditions for a wind simulation.

    Port of the GeoModel BC setup workflow.

    Args:
        wind_direction: Incoming wind direction sector (1-based).
        n_sectors: Total lateral sectors.
        inlet_velocity: Velocity at inlet in m/s.
        sector_base_name: Base name for lateral sector sub-parts.
        top_name: Name of top boundary sub-part.
        bottom_name: Name of bottom boundary sub-part.
        building_name: Name of building surface sub-part (None if no buildings).

    Returns:
        List of BoundaryCondition objects.
    """
    bcs: list[BoundaryCondition] = []
    half = n_sectors // 2
    quarter = n_sectors // 4

    direction = compute_wind_direction_vector(wind_direction, n_sectors)

    # Inlet sectors (upwind half)
    inlet_start = wind_direction - quarter
    for i in range(half):
        s = inlet_start + i
        if s <= 0:
            s += n_sectors
        elif s > n_sectors:
            s -= n_sectors
        bcs.append(InletBC(
            sub_part_name=f"{sector_base_name}{s}",
            velocity=inlet_velocity,
            direction=direction,
        ))

    # Outlet sectors (downwind half)
    outlet_start = wind_direction + half - quarter
    for i in range(half):
        s = outlet_start + i
        if s <= 0:
            s += n_sectors
        elif s > n_sectors:
            s -= n_sectors
        bcs.append(OutletBC(sub_part_name=f"{sector_base_name}{s}"))

    # Top boundary: slip
    bcs.append(SlipBC(sub_part_name=top_name))

    # Bottom/terrain: slip (far from buildings)
    bcs.append(SlipBC(sub_part_name=bottom_name))

    # Building surfaces: no-slip
    if building_name:
        bcs.append(NoSlipBC(sub_part_name=building_name))

    logger.info(f"Created {len(bcs)} boundary conditions for wind_dir={wind_direction}")
    return bcs
