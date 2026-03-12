"""Mesh cleaning utilities.

Port of cleaning_utilities.cpp: isolated node removal, invalid condition
cleanup, and mesh integrity checks.
"""

from __future__ import annotations

import logging

import numpy as np

from ..core.mesh_part import MeshPart

logger = logging.getLogger(__name__)


def clean_isolated_nodes(mesh_part: MeshPart) -> int:
    """Remove nodes not referenced by any element or condition.

    Port of CleaningUtilities::CleanIsolatedNodes.

    Returns:
        Number of nodes removed.
    """
    used_ids = set()

    if mesh_part.elements.count > 0:
        used_ids.update(mesh_part.elements.get_all_node_ids().tolist())
    if mesh_part.conditions.count > 0:
        used_ids.update(mesh_part.conditions.get_all_node_ids().tolist())

    if not used_ids:
        # No elements or conditions → all nodes are isolated
        count = mesh_part.nodes.count
        if count > 0:
            mesh_part.nodes.clear()
            mesh_part.node_data.clear()
            logger.info(f"Removed all {count} nodes (no elements/conditions)")
        return count

    all_ids = set(mesh_part.nodes.ids.tolist())
    isolated = all_ids - used_ids

    if not isolated:
        return 0

    keep_mask = np.array([int(nid) not in isolated for nid in mesh_part.nodes.ids])
    mesh_part.nodes.remove_by_mask(keep_mask)

    for key in list(mesh_part.node_data.keys()):
        mesh_part.node_data[key] = mesh_part.node_data[key][keep_mask]

    logger.info(f"Removed {len(isolated)} isolated nodes")
    return len(isolated)


def clean_invalid_conditions(mesh_part: MeshPart) -> int:
    """Remove conditions whose nodes no longer exist in the mesh.

    Port of CleaningUtilities::CleanConditions.

    Returns:
        Number of conditions removed.
    """
    if mesh_part.conditions.count == 0:
        return 0

    existing_ids = set(int(nid) for nid in mesh_part.nodes.ids)
    keep = np.ones(mesh_part.conditions.count, dtype=bool)

    for i, (cid, conn) in enumerate(mesh_part.conditions):
        for nid in conn:
            if int(nid) not in existing_ids:
                keep[i] = False
                break

    removed = int(np.sum(~keep))
    if removed > 0:
        mesh_part.conditions.remove_by_mask(keep)
        logger.info(f"Removed {removed} invalid conditions")

    return removed


def clean_conditions_at_angles(
    mesh_part: MeshPart,
    skin_sub_part: str = "SKIN_ISOSURFACE",
    bottom_sub_part: str = "BottomModelPart",
) -> int:
    """Remove conditions where all nodes lie on the skin isosurface.

    Port of CleaningUtilities::CleanConditionsAngles.
    Removes corner conditions at the intersection of bottom and skin.

    Returns:
        Number of conditions removed.
    """
    if not mesh_part.has_sub_part(skin_sub_part):
        return 0
    if not mesh_part.has_sub_part(bottom_sub_part):
        return 0

    skin = mesh_part.get_sub_part(skin_sub_part)
    bottom = mesh_part.get_sub_part(bottom_sub_part)

    skin_node_ids = set(int(nid) for nid in skin.nodes.ids)

    if bottom.conditions.count == 0:
        return 0

    keep = np.ones(bottom.conditions.count, dtype=bool)

    for i, (cid, conn) in enumerate(bottom.conditions):
        # Check if all nodes are in skin
        all_in_skin = all(int(nid) in skin_node_ids for nid in conn)
        if all_in_skin:
            keep[i] = False

    removed = int(np.sum(~keep))
    if removed > 0:
        bottom.conditions.remove_by_mask(keep)
        logger.info(f"Removed {removed} conditions at skin angles")

    return removed


def fill_bottom_sub_part(mesh_part: MeshPart) -> None:
    """Assign unclassified conditions to BottomModelPart.

    Port of CleaningUtilities::FillBottom. Conditions not belonging to
    any existing sub-part are assigned to "bottom".

    Args:
        mesh_part: MeshPart with conditions and sub-parts.
    """
    if mesh_part.conditions.count == 0:
        return

    # Collect all condition IDs already in sub-parts
    classified_ids = set()
    for sp_name, sp in mesh_part.sub_parts.items():
        for cid, _ in sp.conditions:
            classified_ids.add(cid)

    # Find unclassified conditions
    unclassified = []
    for cid, conn in mesh_part.conditions:
        if cid not in classified_ids:
            unclassified.append((cid, conn))

    if not unclassified:
        return

    # Create or get bottom sub-part
    bottom_name = "BottomModelPart"
    if not mesh_part.has_sub_part(bottom_name):
        mesh_part.create_sub_part(bottom_name)
    bottom = mesh_part.get_sub_part(bottom_name)

    node_ids_to_add = set()
    for cid, conn in unclassified:
        if not bottom.conditions.has_element(cid):
            bottom.conditions.add(cid, conn)
        for nid in conn:
            node_ids_to_add.add(int(nid))

    for nid in node_ids_to_add:
        if not bottom.nodes.has_node(nid) and mesh_part.nodes.has_node(nid):
            coords = mesh_part.nodes.get_coords(nid)
            bottom.nodes.add(nid, coords[0], coords[1], coords[2])

    logger.info(f"Assigned {len(unclassified)} conditions to {bottom_name}")


def validate_mesh(mesh_part: MeshPart) -> dict:
    """Run basic mesh integrity checks.

    Returns:
        Dictionary with validation results.
    """
    results = {
        "nodes": mesh_part.nodes.count,
        "elements": mesh_part.elements.count,
        "conditions": mesh_part.conditions.count,
        "sub_parts": len(mesh_part.sub_parts),
        "issues": [],
    }

    # Check for degenerate elements
    if mesh_part.elements.count > 0:
        conn = mesh_part.elements.connectivity
        for i in range(conn.shape[0]):
            if len(np.unique(conn[i])) < conn.shape[1]:
                results["issues"].append(
                    f"Degenerate element {int(mesh_part.elements.ids[i])}"
                )

    # Check element connectivity references valid nodes
    existing = set(int(nid) for nid in mesh_part.nodes.ids)
    for container_name, container in [("elements", mesh_part.elements),
                                       ("conditions", mesh_part.conditions)]:
        if container.count > 0:
            all_refs = container.get_all_node_ids()
            invalid = set(int(nid) for nid in all_refs) - existing
            if invalid:
                results["issues"].append(
                    f"{container_name} reference {len(invalid)} non-existent nodes"
                )

    # Check for NaN/Inf in coordinates
    if mesh_part.nodes.count > 0:
        if np.any(~np.isfinite(mesh_part.nodes.coords)):
            results["issues"].append("NaN or Inf in node coordinates")

    results["valid"] = len(results["issues"]) == 0
    return results
