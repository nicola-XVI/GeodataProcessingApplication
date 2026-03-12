"""Volumetric mesh generation using gmsh.

Provides tetrahedral mesh generation from surface meshes,
replacing meshpy.tet for cases requiring finer control over element sizes.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def tetrahedralize_surface(
    mesh_part: MeshPart,
    min_size: float = 1.0,
    max_size: float = 50.0,
    optimize: bool = True,
) -> MeshPart:
    """Generate tetrahedral volume mesh from a closed surface mesh using gmsh.

    Args:
        mesh_part: MeshPart with a closed triangular surface mesh (elements or conditions).
        min_size: Minimum element size.
        max_size: Maximum element size.
        optimize: If True, optimize mesh quality.

    Returns:
        New MeshPart with tetrahedral elements and surface conditions.
    """
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("tetra")

    try:
        # Export surface to temporary STL, then import into gmsh
        container = mesh_part.elements if mesh_part.elements.count > 0 else mesh_part.conditions
        if container.count == 0:
            raise ValueError("No surface elements to tetrahedralize")

        _add_surface_to_gmsh(mesh_part, container)

        # Set mesh size constraints
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", min_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", max_size)

        if optimize:
            gmsh.option.setNumber("Mesh.Optimize", 1)
            gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)

        # Create volume from surface and mesh
        gmsh.model.mesh.classifySurfaces(math.pi, True, True)
        gmsh.model.mesh.createGeometry()
        gmsh.model.mesh.generate(3)

        result = _extract_gmsh_mesh("TetraMesh")

    finally:
        gmsh.finalize()

    logger.info(f"Tetrahedralized: {result.nodes.count} nodes, "
                f"{result.elements.count} elements")
    return result


def tetrahedralize_from_stl(
    stl_path: str,
    min_size: float = 1.0,
    max_size: float = 50.0,
    optimize: bool = True,
) -> MeshPart:
    """Generate tetrahedral volume mesh from an STL file using gmsh.

    Args:
        stl_path: Path to a closed STL surface mesh.
        min_size: Minimum element size.
        max_size: Maximum element size.
        optimize: If True, optimize mesh quality.

    Returns:
        MeshPart with tetrahedral volume mesh.
    """
    import gmsh
    import math

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("tetra_stl")

    try:
        gmsh.merge(stl_path)

        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", min_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", max_size)

        if optimize:
            gmsh.option.setNumber("Mesh.Optimize", 1)
            gmsh.option.setNumber("Mesh.OptimizeNetgen", 1)

        gmsh.model.mesh.classifySurfaces(math.pi, True, True)
        gmsh.model.mesh.createGeometry()

        s = gmsh.model.getEntities(2)
        surface_loop = gmsh.model.geo.addSurfaceLoop([e[1] for e in s])
        gmsh.model.geo.addVolume([surface_loop])
        gmsh.model.geo.synchronize()

        gmsh.model.mesh.generate(3)

        result = _extract_gmsh_mesh("TetraMesh")

    finally:
        gmsh.finalize()

    logger.info(f"Tetrahedralized from STL: {result.nodes.count} nodes, "
                f"{result.elements.count} elements")
    return result


def tetrahedralize_with_size_field(
    stl_path: str,
    size_field_func: callable,
    min_size: float = 1.0,
    max_size: float = 50.0,
) -> MeshPart:
    """Tetrahedralize with a spatially varying size field.

    Args:
        stl_path: Path to closed STL surface.
        size_field_func: Function (x, y, z) -> desired_element_size.
        min_size: Minimum element size.
        max_size: Maximum element size.

    Returns:
        MeshPart with adaptively sized tetrahedral mesh.
    """
    import gmsh
    import math

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.model.add("tetra_field")

    try:
        gmsh.merge(stl_path)

        gmsh.model.mesh.classifySurfaces(math.pi, True, True)
        gmsh.model.mesh.createGeometry()

        s = gmsh.model.getEntities(2)
        surface_loop = gmsh.model.geo.addSurfaceLoop([e[1] for e in s])
        gmsh.model.geo.addVolume([surface_loop])
        gmsh.model.geo.synchronize()

        # Set up callback-based size field
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", min_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", max_size)

        # Use MathEval field with a distance-based expression as fallback
        # For complex fields, use the gmsh Python callback
        gmsh.model.mesh.setSizeCallback(
            lambda dim, tag, x, y, z, lc: size_field_func(x, y, z)
        )

        gmsh.model.mesh.generate(3)
        result = _extract_gmsh_mesh("AdaptiveTetraMesh")

    finally:
        gmsh.finalize()

    return result


def _add_surface_to_gmsh(mesh_part: MeshPart, container) -> None:
    """Add a surface mesh from MeshPart into the current gmsh model."""
    import gmsh

    # Get unique node IDs and their coordinates
    used_ids = container.get_all_node_ids()
    id_to_gmsh = {}

    for nid in used_ids:
        nid = int(nid)
        coords = mesh_part.nodes.get_coords(nid)
        tag = gmsh.model.occ.addPoint(coords[0], coords[1], coords[2])
        id_to_gmsh[nid] = tag

    gmsh.model.occ.synchronize()


def _extract_gmsh_mesh(name: str = "GmshMesh") -> MeshPart:
    """Extract mesh data from current gmsh model into a MeshPart."""
    import gmsh

    mp = MeshPart(name=name)

    # Get nodes
    node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
    n_nodes = len(node_tags)
    coords = np.array(node_coords, dtype=np.float64).reshape(-1, 3)
    ids = np.array(node_tags, dtype=np.int64)
    mp.create_nodes_bulk(ids, coords)

    # Get elements by type
    elem_types, elem_tags_list, elem_node_tags_list = gmsh.model.mesh.getElements()

    elem_id_counter = 1
    for etype, etags, enodes in zip(elem_types, elem_tags_list, elem_node_tags_list):
        etype_name = gmsh.model.mesh.getElementProperties(etype)
        type_name = etype_name[0]  # e.g., "Tetrahedron 4", "Triangle 3"
        nodes_per = etype_name[3]  # number of nodes per element

        n_elems = len(etags)
        enodes = np.array(enodes, dtype=np.int64).reshape(n_elems, nodes_per)
        eids = np.array(etags, dtype=np.int64)

        if nodes_per == 4 and "Tetrahedron" in type_name:
            mp.create_elements_bulk("tet4", eids, enodes)
        elif nodes_per == 3 and "Triangle" in type_name:
            mp.create_conditions_bulk("tri3", eids, enodes)

    return mp
