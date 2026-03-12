"""Adaptive mesh refinement using gmsh.

Replaces MMG/ParMMG refinement with gmsh field-based adaptive refinement.
Supports distance-based, box-based, and custom size field refinement.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def refine_near_surface(
    mesh_part: MeshPart,
    surface_mesh: MeshPart,
    min_size: float = 1.0,
    max_size: float = 50.0,
    distance_threshold: float = 10.0,
    interpolation: str = "linear",
) -> MeshPart:
    """Refine a volume mesh near a reference surface.

    Uses gmsh distance field from the surface to control element size.
    Replaces MMG's distance-based refinement.

    Args:
        mesh_part: Volume mesh to refine.
        surface_mesh: Reference surface (e.g., ground or buildings).
        min_size: Element size at the surface.
        max_size: Element size far from the surface.
        distance_threshold: Distance over which size transitions.
        interpolation: "linear" or "exponential" size transition.

    Returns:
        Refined MeshPart.
    """
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("refine")

    try:
        # Write the volume mesh to temporary file and reimport
        with tempfile.TemporaryDirectory() as tmpdir:
            vol_path = str(Path(tmpdir) / "volume.vtk")
            surf_path = str(Path(tmpdir) / "surface.stl")

            from ..io.writers import write_vtk, write_stl
            write_vtk(mesh_part, vol_path)
            write_stl(surface_mesh, surf_path)

            gmsh.merge(vol_path)

            # Add distance field from surface
            gmsh.merge(surf_path)

        # Create distance field
        dist_field = gmsh.model.mesh.field.add("Distance")
        # Use all surface entities
        surfaces = gmsh.model.getEntities(2)
        if surfaces:
            gmsh.model.mesh.field.setNumbers(dist_field, "SurfacesList",
                                              [s[1] for s in surfaces])

        # Create threshold field for size interpolation
        thresh_field = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(thresh_field, "InField", dist_field)
        gmsh.model.mesh.field.setNumber(thresh_field, "SizeMin", min_size)
        gmsh.model.mesh.field.setNumber(thresh_field, "SizeMax", max_size)
        gmsh.model.mesh.field.setNumber(thresh_field, "DistMin", 0.0)
        gmsh.model.mesh.field.setNumber(thresh_field, "DistMax", distance_threshold)

        if interpolation == "exponential":
            gmsh.model.mesh.field.setNumber(thresh_field, "Sigmoid", 1)

        gmsh.model.mesh.field.setAsBackgroundMesh(thresh_field)

        gmsh.option.setNumber("Mesh.CharacteristicLengthFromPoints", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthExtendFromBoundary", 0)

        gmsh.model.mesh.generate(3)

        from .tetrahedralization import _extract_gmsh_mesh
        result = _extract_gmsh_mesh("RefinedMesh")

    finally:
        gmsh.finalize()

    logger.info(f"Refined mesh: {result.nodes.count} nodes, "
                f"{result.elements.count} elements")
    return result


def refine_with_distance_field(
    mesh_part: MeshPart,
    distance_values: np.ndarray,
    min_size: float = 1.0,
    max_size: float = 50.0,
    distance_threshold: float = 10.0,
) -> MeshPart:
    """Refine using a pre-computed distance field on nodes.

    Args:
        mesh_part: Volume mesh to refine.
        distance_values: Per-node distance values.
        min_size: Element size where distance is small.
        max_size: Element size where distance is large.
        distance_threshold: Distance at which max_size is reached.

    Returns:
        Refined MeshPart.
    """
    # Compute desired size at each node
    t = np.clip(np.abs(distance_values) / distance_threshold, 0, 1)
    desired_sizes = min_size + t * (max_size - min_size)

    def size_callback(x, y, z):
        from scipy.spatial import cKDTree
        if not hasattr(size_callback, '_tree'):
            size_callback._tree = cKDTree(mesh_part.nodes.coords)
            size_callback._sizes = desired_sizes
        _, idx = size_callback._tree.query([x, y, z])
        return float(size_callback._sizes[idx])

    from .tetrahedralization import tetrahedralize_with_size_field
    import tempfile
    from ..io.writers import write_stl

    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = str(Path(tmpdir) / "surface.stl")
        write_stl(mesh_part, stl_path, use_elements=False)

        result = tetrahedralize_with_size_field(
            stl_path, size_callback,
            min_size=min_size, max_size=max_size,
        )

    return result


def compute_refinement_sizes(
    node_coords: np.ndarray,
    reference_points: np.ndarray,
    min_size: float = 1.0,
    max_size: float = 50.0,
    boundary_layer_distance: float = 2.0,
    interpolation: str = "linear",
) -> np.ndarray:
    """Compute desired element sizes based on distance to reference geometry.

    Args:
        node_coords: (N, 3) node positions.
        reference_points: (M, 3) reference surface points.
        min_size: Size near the reference.
        max_size: Size far from reference.
        boundary_layer_distance: Distance for transition.
        interpolation: "linear", "exponential", or "constant".

    Returns:
        (N,) array of desired element sizes.
    """
    from scipy.spatial import cKDTree

    tree = cKDTree(reference_points)
    distances, _ = tree.query(node_coords)

    t = np.clip(distances / boundary_layer_distance, 0, 1)

    if interpolation == "linear":
        sizes = min_size + t * (max_size - min_size)
    elif interpolation == "exponential":
        sizes = min_size * (max_size / min_size) ** t
    elif interpolation == "constant":
        sizes = np.where(distances < boundary_layer_distance, min_size, max_size)
    else:
        raise ValueError(f"Unknown interpolation: {interpolation}")

    return sizes
