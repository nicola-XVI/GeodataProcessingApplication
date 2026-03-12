"""Cylindrical domain construction with terrain points.

Port of geo_mesher.py MeshCircleWithTerrainPoints_old.
Creates a closed cylindrical volume mesh around terrain geometry,
with bottom (terrain), top (flat), and lateral (cylinder wall) boundaries.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

from ..core.mesh_part import MeshPart
from ..core.containers import ElementContainer

logger = logging.getLogger(__name__)


def create_cylindrical_domain(
    terrain: MeshPart,
    height_offset: float = 0.0,
    circ_division: int = 60,
    num_sectors: int = 12,
    ground_radius_ratio: float = 0.8,
    building_radius_ratio: float = 0.6,
) -> MeshPart:
    """Create a cylindrical volumetric mesh enclosing terrain.

    Port of MeshCircleWithTerrainPoints_old. Builds a closed cylinder:
    - Bottom: terrain surface (triangulated)
    - Top: flat cap at max_z + height_offset
    - Lateral: cylinder wall

    Then tetrahedralizes the enclosed volume.

    Args:
        terrain: MeshPart with terrain nodes (and optionally elements).
        height_offset: Extra height above terrain max Z.
        circ_division: Number of divisions around the circumference.
        num_sectors: Number of wind sectors (circ_division is adjusted to be divisible).
        ground_radius_ratio: Ratio r_ground/r_boundary for terrain Z-smoothing.
        building_radius_ratio: Ratio r_buildings/r_boundary.

    Returns:
        MeshPart with tetrahedral volume mesh and sub-parts:
        BottomModelPart, TopModelPart, LateralModelPart.
    """
    import triangle as tr

    # Adjust circ_division to be divisible by num_sectors
    circ_division = num_sectors * max(1, round(circ_division / num_sectors))

    coords = terrain.nodes.coords
    x_min, x_max = coords[:, 0].min(), coords[:, 0].max()
    y_min, y_max = coords[:, 1].min(), coords[:, 1].max()
    x_center = (x_min + x_max) / 2.0
    y_center = (y_min + y_max) / 2.0

    r_boundary = min(x_max - x_min, y_max - y_min) / 2.0
    r_ground = r_boundary * ground_radius_ratio
    delta = r_boundary / 20.0

    # Step 1: Filter nodes inside cylinder, collect interior coords
    dists = np.sqrt((coords[:, 0] - x_center) ** 2 + (coords[:, 1] - y_center) ** 2)
    inside_mask = dists <= (r_boundary - delta)

    interior_coords = coords[inside_mask]
    if len(interior_coords) == 0:
        raise ValueError("No terrain nodes inside the cylindrical domain")

    z_min = interior_coords[:, 2].min()
    z_max = interior_coords[:, 2].max()

    # Step 2: Z-smoothing for nodes between r_ground and r_boundary
    interior_dists = dists[inside_mask]
    smoothed_z = interior_coords[:, 2].copy()

    smooth_mask = interior_dists > r_ground
    if smooth_mask.any():
        beta = 1.0 - (interior_dists[smooth_mask] - r_ground) / (r_boundary - delta - r_ground)
        beta = np.clip(beta, 0, 1)
        smoothed_z[smooth_mask] = (interior_coords[smooth_mask, 2] - z_min) * beta + z_min

    # Step 3: Generate circumference points
    theta = np.linspace(0, 2 * math.pi, circ_division, endpoint=False)
    circle_x = r_boundary * np.cos(theta) + x_center
    circle_y = r_boundary * np.sin(theta) + y_center

    # Step 4: 2D triangulation (terrain + circle boundary)
    n_interior = len(interior_coords)
    n_circle = len(circle_x)

    vertices_2d = np.zeros((n_interior + n_circle, 2))
    vertices_2d[:n_interior, 0] = interior_coords[:, 0]
    vertices_2d[:n_interior, 1] = interior_coords[:, 1]
    vertices_2d[n_interior:, 0] = circle_x
    vertices_2d[n_interior:, 1] = circle_y

    tri_input = dict(vertices=vertices_2d.tolist())
    tri_result = tr.triangulate(tri_input)
    triangles_2d = np.array(tri_result["triangles"], dtype=np.int64)
    verts_2d = np.array(tri_result["vertices"])

    # Step 5: Build 3D points - bottom layer + top layer
    n_2d = len(verts_2d)
    volume_height = z_max + height_offset

    # Bottom layer Z: use smoothed Z for interior, z_min for circle and new points
    bottom_z = np.full(n_2d, z_min)
    # Interior points keep their smoothed Z
    for i in range(min(n_interior, n_2d)):
        if i < len(smoothed_z):
            bottom_z[i] = smoothed_z[i]

    bottom_points = np.column_stack([verts_2d, bottom_z])
    top_points = np.column_stack([
        verts_2d,
        np.full(n_2d, volume_height),
    ])

    all_points = np.vstack([bottom_points, top_points])

    # Step 6: Build facets for tetrahedralization
    # Bottom faces (marker=1)
    bottom_facets = triangles_2d.tolist()
    bottom_markers = [1] * len(triangles_2d)

    # Top faces (marker=2) - offset by n_2d
    top_facets = (triangles_2d + n_2d).tolist()
    top_markers = [2] * len(triangles_2d)

    # Lateral faces (marker=3) - connect circle bottom to circle top
    # Circle points start at index n_interior in the 2D triangulation
    # But triangle lib may have reindexed, so we use the original circle indices
    lateral_facets = []
    lateral_markers = []
    for i in range(n_circle):
        i_next = (i + 1) % n_circle
        b0 = n_interior + i
        b1 = n_interior + i_next
        t0 = n_2d + n_interior + i
        t1 = n_2d + n_interior + i_next
        # Two triangles per quad
        lateral_facets.append([b0, b1, t1])
        lateral_facets.append([b0, t1, t0])
        lateral_markers.extend([3, 3])

    all_facets = bottom_facets + top_facets + lateral_facets
    all_markers = bottom_markers + top_markers + lateral_markers

    # Step 7: Tetrahedralize
    result_mp = _tetrahedralize_domain(all_points, all_facets, all_markers)

    # Store domain metadata
    result_mp.process_info["X_CENTER"] = x_center
    result_mp.process_info["Y_CENTER"] = y_center
    result_mp.process_info["R_BOUNDARY"] = r_boundary
    result_mp.process_info["R_GROUND"] = r_ground
    result_mp.process_info["R_BUILDINGS"] = r_boundary * building_radius_ratio
    result_mp.process_info["Z_MIN"] = z_min
    result_mp.process_info["Z_MAX"] = z_max
    result_mp.process_info["VOLUME_HEIGHT"] = volume_height

    logger.info(f"Created cylindrical domain: {result_mp.nodes.count} nodes, "
                f"{result_mp.elements.count} elements, "
                f"{result_mp.conditions.count} conditions")
    return result_mp


def _tetrahedralize_domain(
    points: np.ndarray,
    facets: list[list[int]],
    markers: list[int],
) -> MeshPart:
    """Tetrahedralize a closed surface domain using meshpy.tet.

    Returns MeshPart with sub-parts: BottomModelPart, TopModelPart, LateralModelPart.
    """
    from meshpy.tet import MeshInfo, build

    mesh_info = MeshInfo()
    mesh_info.set_points(points.tolist())
    mesh_info.set_facets(facets, markers=markers)

    mesh = build(mesh_info)

    # Build MeshPart
    mp = MeshPart(name="Domain")

    # Add nodes (1-based IDs)
    n_nodes = len(mesh.points)
    node_ids = np.arange(1, n_nodes + 1, dtype=np.int64)
    node_coords = np.array(mesh.points, dtype=np.float64)
    mp.create_nodes_bulk(node_ids, node_coords)

    # Add tetrahedral elements (1-based IDs)
    n_elems = len(mesh.elements)
    if n_elems > 0:
        elem_ids = np.arange(1, n_elems + 1, dtype=np.int64)
        elem_conn = np.array(mesh.elements, dtype=np.int64) + 1  # to 1-based
        mp.create_elements_bulk("tet4", elem_ids, elem_conn)

    # Add surface conditions (1-based IDs)
    n_faces = len(mesh.faces)
    if n_faces > 0:
        cond_ids = np.arange(1, n_faces + 1, dtype=np.int64)
        cond_conn = np.array(mesh.faces, dtype=np.int64) + 1  # to 1-based
        mp.create_conditions_bulk("tri3", cond_ids, cond_conn)

    # Create sub-parts by face marker
    marker_to_name = {1: "BottomModelPart", 2: "TopModelPart", 3: "LateralModelPart"}
    face_markers = list(mesh.face_markers)

    for marker_val, sub_name in marker_to_name.items():
        sub = mp.create_sub_part(sub_name)
        sub_cond_ids = []
        sub_node_ids = set()

        for i, m in enumerate(face_markers):
            if m == marker_val:
                cid = i + 1
                sub_cond_ids.append(cid)
                conn = mp.conditions.get_node_ids(cid)
                for nid in conn:
                    sub_node_ids.add(int(nid))

        if sub_cond_ids:
            mp.add_conditions_to_sub_part(sub_name, sub_cond_ids)
        if sub_node_ids:
            mp.add_nodes_to_sub_part(sub_name, list(sub_node_ids))

    return mp


def create_sectors(
    mesh_part: MeshPart,
    n_sectors: int = 12,
    x_center: Optional[float] = None,
    y_center: Optional[float] = None,
) -> None:
    """Split the LateralModelPart into angular sectors for wind directions.

    Port of geo_mesher.py MeshSectors. Creates LateralSector_1..N sub-parts.

    Args:
        mesh_part: MeshPart with LateralModelPart sub-part.
        n_sectors: Number of angular sectors.
        x_center: Domain center X (from process_info if None).
        y_center: Domain center Y (from process_info if None).
    """
    if not mesh_part.has_sub_part("LateralModelPart"):
        logger.warning("No LateralModelPart found, skipping sector creation")
        return

    if x_center is None:
        x_center = mesh_part.process_info.get("X_CENTER", 0.0)
    if y_center is None:
        y_center = mesh_part.process_info.get("Y_CENTER", 0.0)

    lateral = mesh_part.get_sub_part("LateralModelPart")

    # Define sector angle ranges
    sector_size = 360.0 / n_sectors
    sectors = {}
    for i in range(n_sectors):
        sectors[i + 1] = (i * sector_size, (i + 1) * sector_size)

    # Create sector sub-parts
    for sector_id in range(1, n_sectors + 1):
        name = f"LateralSector_{sector_id}"
        if not mesh_part.has_sub_part(name):
            mesh_part.create_sub_part(name)

    # Classify conditions by angle
    if lateral.conditions.count == 0:
        logger.warning("LateralModelPart has no conditions")
        return

    for cond_id, conn in lateral.conditions:
        # Compute condition centroid
        centroid = np.zeros(3)
        for nid in conn:
            centroid += mesh_part.nodes.get_coords(int(nid))
        centroid /= len(conn)

        # Compute angle from center
        dx = centroid[0] - x_center
        dy = centroid[1] - y_center
        angle = math.degrees(math.atan2(dy, dx))
        if angle < 0:
            angle += 360.0

        # Find sector
        for sector_id, (a_start, a_end) in sectors.items():
            if a_start <= angle < a_end:
                sub_name = f"LateralSector_{sector_id}"
                sub = mesh_part.get_sub_part(sub_name)

                # Add condition
                if not sub.conditions.has_element(cond_id):
                    sub.conditions.add(cond_id, conn)

                # Add nodes
                for nid in conn:
                    nid = int(nid)
                    if not sub.nodes.has_node(nid):
                        coords = mesh_part.nodes.get_coords(nid)
                        sub.nodes.add(nid, coords[0], coords[1], coords[2])
                break

    # Remove original LateralModelPart
    mesh_part.remove_sub_part("LateralModelPart")

    logger.info(f"Created {n_sectors} lateral sectors")
