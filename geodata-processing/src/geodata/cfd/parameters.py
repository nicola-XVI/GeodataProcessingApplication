"""CFD solver parameter generation.

Port of GeoModel._parameter_initialization and BC parameter methods.
Generates JSON configuration files for Kratos FluidDynamicsApplication
or other CFD solvers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .boundary import (
    BoundaryCondition,
    InletBC,
    NoSlipBC,
    OutletBC,
    SlipBC,
)

logger = logging.getLogger(__name__)


def generate_kratos_parameters(
    problem_name: str,
    volume_part_name: str = "Parts_Fluid",
    boundary_conditions: Optional[list[BoundaryCondition]] = None,
    solver_type: str = "Monolithic",
    time_step: float = 0.1,
    end_time: float = 1.0,
    density: float = 1.0,
    dynamic_viscosity: float = 0.002,
    gravity_modulus: float = 0.0,
    gravity_direction: list[float] = None,
) -> dict:
    """Generate Kratos FluidDynamicsApplication JSON parameters.

    Port of GeoModel._parameter_initialization + NoSlip/Slip/Inlet/Outlet/PartsFluid.

    Args:
        problem_name: Name of the problem (used for filenames).
        volume_part_name: Name of the volume sub-model-part.
        boundary_conditions: List of boundary condition objects.
        solver_type: "Monolithic" or "FractionalStep".
        time_step: Time step size.
        end_time: Simulation end time.
        density: Fluid density.
        dynamic_viscosity: Fluid dynamic viscosity.
        gravity_modulus: Gravity magnitude (0 to disable).
        gravity_direction: Gravity direction vector.

    Returns:
        Dict with complete Kratos solver parameters.
    """
    if gravity_direction is None:
        gravity_direction = [0.0, -1.0, 0.0]

    if boundary_conditions is None:
        boundary_conditions = []

    # Collect skin parts from BCs
    skin_parts = []
    bc_process_list = []

    for bc in boundary_conditions:
        skin_parts.append(bc.sub_part_name)

        if isinstance(bc, NoSlipBC):
            bc_process_list.append(_noslip_params(bc))
        elif isinstance(bc, SlipBC):
            bc_process_list.append(_slip_params(bc))
        elif isinstance(bc, InletBC):
            bc_process_list.append(_inlet_params(bc))
        elif isinstance(bc, OutletBC):
            bc_process_list.append(_outlet_params(bc))

    params = {
        "problem_data": {
            "problem_name": problem_name,
            "parallel_type": "OpenMP",
            "echo_level": 0,
            "start_time": 0.0,
            "end_time": end_time,
        },
        "output_processes": {
            "gid_output": [
                {
                    "python_module": "gid_output_process",
                    "kratos_module": "KratosMultiphysics",
                    "process_name": "GiDOutputProcess",
                    "help": "This process writes postprocessing files for GiD",
                    "Parameters": {
                        "model_part_name": "FluidModelPart.fluid_computational_model_part",
                        "output_name": problem_name,
                        "postprocess_parameters": {
                            "result_file_configuration": {
                                "gidpost_flags": {
                                    "GiDPostMode": "GiD_PostBinary",
                                    "WriteDeformedMeshFlag": "WriteDeformed",
                                    "WriteConditionsFlag": "WriteConditions",
                                    "MultiFileFlag": "SingleFile",
                                },
                                "file_label": "time",
                                "output_control_type": "step",
                                "output_interval": 1,
                                "body_output": True,
                                "node_output": False,
                                "skin_output": False,
                                "plane_output": [],
                                "nodal_results": ["VELOCITY", "PRESSURE"],
                                "gauss_point_results": [],
                                "nodal_nonhistorical_results": [],
                            },
                            "point_data_configuration": [],
                        },
                    },
                }
            ]
        },
        "solver_settings": {
            "model_part_name": "FluidModelPart",
            "domain_size": 3,
            "solver_type": solver_type,
            "model_import_settings": {
                "input_type": "mdpa",
                "input_filename": problem_name,
            },
            "echo_level": 0,
            "compute_reactions": False,
            "maximum_iterations": 10,
            "relative_velocity_tolerance": 0.001,
            "absolute_velocity_tolerance": 1e-5,
            "relative_pressure_tolerance": 0.001,
            "absolute_pressure_tolerance": 1e-5,
            "volume_model_part_name": volume_part_name,
            "skin_parts": skin_parts,
            "no_skin_parts": [],
            "time_scheme": "bossak",
            "time_stepping": {
                "automatic_time_step": False,
                "time_step": time_step,
            },
            "formulation": {
                "element_type": "vms",
                "use_orthogonal_subscales": False,
                "dynamic_tau": 1.0,
            },
            "reform_dofs_at_each_step": False,
        },
        "processes": {
            "initial_conditions_process_list": [],
            "boundary_conditions_process_list": bc_process_list,
            "gravity": [
                {
                    "python_module": "assign_vector_by_direction_process",
                    "kratos_module": "KratosMultiphysics",
                    "process_name": "AssignVectorByDirectionProcess",
                    "Parameters": {
                        "model_part_name": f"FluidModelPart.{volume_part_name}",
                        "variable_name": "BODY_FORCE",
                        "modulus": gravity_modulus,
                        "constrained": False,
                        "direction": gravity_direction,
                    },
                }
            ],
            "auxiliar_process_list": [],
        },
    }

    return params


def _noslip_params(bc: NoSlipBC) -> dict:
    """Generate NoSlip process parameters."""
    return {
        "python_module": "apply_noslip_process",
        "kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
        "process_name": "ApplyNoSlipProcess",
        "Parameters": {
            "model_part_name": f"FluidModelPart.{bc.sub_part_name}",
        },
    }


def _slip_params(bc: SlipBC) -> dict:
    """Generate Slip process parameters."""
    return {
        "python_module": "apply_slip_process",
        "kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
        "process_name": "ApplySlipProcess",
        "Parameters": {
            "model_part_name": f"FluidModelPart.{bc.sub_part_name}",
        },
    }


def _inlet_params(bc: InletBC) -> dict:
    """Generate Inlet process parameters."""
    return {
        "python_module": "apply_inlet_process",
        "kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
        "process_name": "ApplyInletProcess",
        "Parameters": {
            "model_part_name": f"FluidModelPart.{bc.sub_part_name}",
            "variable_name": "VELOCITY",
            "interval": bc.interval,
            "modulus": bc.velocity,
            "direction": bc.direction,
        },
    }


def _outlet_params(bc: OutletBC) -> dict:
    """Generate Outlet process parameters."""
    return {
        "python_module": "apply_outlet_process",
        "kratos_module": "KratosMultiphysics.FluidDynamicsApplication",
        "process_name": "ApplyOutletProcess",
        "Parameters": {
            "model_part_name": f"FluidModelPart.{bc.sub_part_name}",
            "variable_name": "PRESSURE",
            "constrained": True,
            "value": bc.pressure,
            "hydrostatic_outlet": bc.hydrostatic,
            "h_top": bc.h_top,
        },
    }


def write_parameters_json(
    params: dict,
    file_out: str,
) -> str:
    """Write solver parameters to a JSON file.

    Args:
        params: Parameters dict (from generate_kratos_parameters).
        file_out: Output file path.

    Returns:
        Path to the written file.
    """
    os.makedirs(os.path.dirname(file_out) or ".", exist_ok=True)

    with open(file_out, "w") as f:
        json.dump(params, f, indent=4)

    logger.info(f"Wrote CFD parameters to {file_out}")
    return file_out
