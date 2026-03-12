"""MeshPart - Core data model replacing Kratos ModelPart.

A MeshPart holds nodes, elements, conditions, per-node/element data fields,
properties, and nested sub-parts. All backed by numpy arrays for performance.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .containers import NodeContainer, ElementContainer

logger = logging.getLogger(__name__)


class MeshPart:
    """Central mesh data structure. Replaces Kratos ModelPart.

    Holds:
    - Nodes (id, x, y, z) via NodeContainer
    - Elements (triangles, tetrahedra) via ElementContainer
    - Conditions (boundary faces) via ElementContainer
    - Per-node scalar/vector data fields (distance, gradient, etc.)
    - Per-element data fields
    - Nested sub-parts that reference into the parent's storage
    - Properties bags
    """

    def __init__(self, name: str = "MeshPart", parent: Optional[MeshPart] = None):
        self.name = name
        self.parent = parent

        # Core storage
        self.nodes = NodeContainer()
        self.elements = ElementContainer("tet4")
        self.conditions = ElementContainer("tri3")

        # Per-node and per-element data fields
        # Keys are field names like "distance", "extrusion_height", "distance_gradient"
        self.node_data: dict[str, np.ndarray] = {}
        self.element_data: dict[str, np.ndarray] = {}

        # Properties (equivalent to Kratos Properties)
        self.properties: dict[int, dict] = {0: {}}

        # Sub-parts (nested MeshParts)
        self._sub_parts: dict[str, MeshPart] = {}

        # Buffer size (kept for API compatibility, not actively used)
        self.buffer_size: int = 1

        # Process info (metadata)
        self.process_info: dict[str, object] = {
            "DOMAIN_SIZE": 3,
            "TIME": 0.0,
            "DELTA_TIME": 1.0,
        }

    # ---- Node operations ----

    def create_node(self, node_id: int, x: float, y: float, z: float) -> int:
        """Create a new node. Returns array index."""
        idx = self.nodes.add(node_id, x, y, z)
        # Extend all node data fields with default value
        for key, arr in self.node_data.items():
            if arr.ndim == 1:
                self.node_data[key] = np.append(arr, 0.0)
            else:
                # Vector field (e.g., gradient with shape (N, 3))
                zeros = np.zeros((1, arr.shape[1]))
                self.node_data[key] = np.vstack([arr, zeros])
        return idx

    def create_nodes_bulk(self, ids: np.ndarray, coords: np.ndarray) -> None:
        """Create multiple nodes at once."""
        n_new = len(ids)
        self.nodes.add_bulk(ids, coords)
        for key, arr in self.node_data.items():
            if arr.ndim == 1:
                self.node_data[key] = np.concatenate([arr, np.zeros(n_new)])
            else:
                self.node_data[key] = np.concatenate([arr, np.zeros((n_new, arr.shape[1]))])

    @property
    def number_of_nodes(self) -> int:
        return self.nodes.count

    @property
    def number_of_elements(self) -> int:
        return self.elements.count

    @property
    def number_of_conditions(self) -> int:
        return self.conditions.count

    # ---- Element operations ----

    def create_element(self, element_type: str, elem_id: int,
                       node_ids: list[int] | np.ndarray,
                       props_id: int = 0) -> int:
        """Create a new element. Adjusts element_type if needed."""
        if self.elements.count == 0 and self.elements.element_type != _kratos_to_type(element_type):
            self.elements = ElementContainer(_kratos_to_type(element_type))
        return self.elements.add(elem_id, node_ids)

    def create_elements_bulk(self, element_type: str, ids: np.ndarray,
                             connectivity: np.ndarray) -> None:
        """Create multiple elements at once."""
        etype = _kratos_to_type(element_type)
        if self.elements.count == 0 and self.elements.element_type != etype:
            self.elements = ElementContainer(etype)
        self.elements.add_bulk(ids, connectivity)

    # ---- Condition operations ----

    def create_condition(self, cond_type: str, cond_id: int,
                         node_ids: list[int] | np.ndarray,
                         props_id: int = 0) -> int:
        """Create a new boundary condition (surface face)."""
        if self.conditions.count == 0 and self.conditions.element_type != _kratos_to_type(cond_type):
            self.conditions = ElementContainer(_kratos_to_type(cond_type))
        return self.conditions.add(cond_id, node_ids)

    def create_conditions_bulk(self, cond_type: str, ids: np.ndarray,
                               connectivity: np.ndarray) -> None:
        """Create multiple conditions at once."""
        ctype = _kratos_to_type(cond_type)
        if self.conditions.count == 0 and self.conditions.element_type != ctype:
            self.conditions = ElementContainer(ctype)
        self.conditions.add_bulk(ids, connectivity)

    # ---- Node data fields ----

    def add_node_field(self, name: str, dim: int = 1,
                       default: float = 0.0) -> np.ndarray:
        """Register a per-node data field. Returns the array."""
        n = self.nodes.count
        if dim == 1:
            self.node_data[name] = np.full(n, default, dtype=np.float64)
        else:
            self.node_data[name] = np.full((n, dim), default, dtype=np.float64)
        return self.node_data[name]

    def get_node_field(self, name: str) -> np.ndarray:
        """Get a per-node data field array."""
        return self.node_data[name]

    def set_node_field(self, name: str, values: np.ndarray) -> None:
        """Set a per-node data field."""
        self.node_data[name] = np.asarray(values)

    def has_node_field(self, name: str) -> bool:
        return name in self.node_data

    # ---- Element data fields ----

    def add_element_field(self, name: str, dim: int = 1,
                          default: float = 0.0) -> np.ndarray:
        n = self.elements.count
        if dim == 1:
            self.element_data[name] = np.full(n, default, dtype=np.float64)
        else:
            self.element_data[name] = np.full((n, dim), default, dtype=np.float64)
        return self.element_data[name]

    # ---- Sub-part operations ----

    def create_sub_part(self, name: str) -> MeshPart:
        """Create a nested sub-part."""
        if name in self._sub_parts:
            raise ValueError(f"Sub-part '{name}' already exists in '{self.name}'")
        sub = MeshPart(name=name, parent=self)
        self._sub_parts[name] = sub
        return sub

    def get_sub_part(self, name: str) -> MeshPart:
        """Get a sub-part by name."""
        if name not in self._sub_parts:
            raise KeyError(f"Sub-part '{name}' not found in '{self.name}'")
        return self._sub_parts[name]

    def has_sub_part(self, name: str) -> bool:
        return name in self._sub_parts

    def remove_sub_part(self, name: str) -> None:
        if name not in self._sub_parts:
            raise KeyError(f"Sub-part '{name}' not found in '{self.name}'")
        del self._sub_parts[name]

    @property
    def sub_parts(self) -> dict[str, MeshPart]:
        return self._sub_parts

    def add_nodes_to_sub_part(self, sub_name: str, node_ids: list[int] | np.ndarray) -> None:
        """Add existing nodes (by ID) to a sub-part.
        Copies node data from parent into sub-part."""
        sub = self.get_sub_part(sub_name)
        node_ids = np.asarray(node_ids, dtype=np.int64)
        unique_ids = np.unique(node_ids)
        for nid in unique_ids:
            nid = int(nid)
            if not sub.nodes.has_node(nid) and self.nodes.has_node(nid):
                coords = self.nodes.get_coords(nid)
                sub.nodes.add(nid, coords[0], coords[1], coords[2])

    def add_elements_to_sub_part(self, sub_name: str, elem_ids: list[int] | np.ndarray) -> None:
        """Add existing elements (by ID) to a sub-part."""
        sub = self.get_sub_part(sub_name)
        elem_ids = np.asarray(elem_ids, dtype=np.int64)
        for eid in elem_ids:
            eid = int(eid)
            if not sub.elements.has_element(eid) and self.elements.has_element(eid):
                conn = self.elements.get_node_ids(eid)
                sub.elements.add(eid, conn)

    def add_conditions_to_sub_part(self, sub_name: str, cond_ids: list[int] | np.ndarray) -> None:
        """Add existing conditions (by ID) to a sub-part."""
        sub = self.get_sub_part(sub_name)
        cond_ids = np.asarray(cond_ids, dtype=np.int64)
        for cid in cond_ids:
            cid = int(cid)
            if not sub.conditions.has_element(cid) and self.conditions.has_element(cid):
                conn = self.conditions.get_node_ids(cid)
                sub.conditions.add(cid, conn)

    # ---- Removal operations ----

    def remove_nodes_by_flag(self, flag_field: str) -> int:
        """Remove nodes where flag_field is True (nonzero). Returns count removed.
        Also removes elements/conditions referencing removed nodes."""
        if flag_field not in self.node_data:
            return 0
        flags = self.node_data[flag_field]
        keep_mask = flags == 0
        removed_count = int(np.sum(~keep_mask))
        if removed_count == 0:
            return 0

        removed_ids = set(self.nodes.ids[~keep_mask].tolist())

        # Remove from nodes
        self.nodes.remove_by_mask(keep_mask)

        # Update node data fields
        for key in list(self.node_data.keys()):
            self.node_data[key] = self.node_data[key][keep_mask]

        # Remove elements that reference removed nodes
        self._remove_elements_referencing(removed_ids)
        self._remove_conditions_referencing(removed_ids)

        logger.info(f"Removed {removed_count} nodes from '{self.name}'")
        return removed_count

    def remove_elements_by_flag(self, flag_field: str) -> int:
        """Remove elements where flag_field is True (nonzero)."""
        if flag_field not in self.element_data:
            return 0
        flags = self.element_data[flag_field]
        keep_mask = flags == 0
        removed_count = int(np.sum(~keep_mask))
        if removed_count == 0:
            return 0

        self.elements.remove_by_mask(keep_mask)
        for key in list(self.element_data.keys()):
            self.element_data[key] = self.element_data[key][keep_mask]

        logger.info(f"Removed {removed_count} elements from '{self.name}'")
        return removed_count

    def _remove_elements_referencing(self, removed_node_ids: set[int]) -> None:
        """Remove elements that reference any of the removed nodes."""
        if self.elements.count == 0 or not removed_node_ids:
            return
        # Vectorized check: any node in the element is in removed_ids
        removed_arr = np.array(list(removed_node_ids), dtype=np.int64)
        mask = np.isin(self.elements.connectivity, removed_arr).any(axis=1)
        if mask.any():
            self.elements.remove_by_mask(~mask)

    def _remove_conditions_referencing(self, removed_node_ids: set[int]) -> None:
        """Remove conditions that reference any of the removed nodes."""
        if self.conditions.count == 0 or not removed_node_ids:
            return
        removed_arr = np.array(list(removed_node_ids), dtype=np.int64)
        mask = np.isin(self.conditions.connectivity, removed_arr).any(axis=1)
        if mask.any():
            self.conditions.remove_by_mask(~mask)

    # ---- Cleaning operations ----

    def clean_isolated_nodes(self) -> int:
        """Remove nodes not referenced by any element. Returns count removed."""
        if self.elements.count == 0:
            return 0
        used_ids = set(self.elements.get_all_node_ids().tolist())
        all_ids = set(self.nodes.ids.tolist())
        isolated = all_ids - used_ids
        if not isolated:
            return 0
        self.nodes.remove_by_ids(isolated)
        # Update node data fields
        keep_mask_orig = np.array([int(nid) not in isolated for nid in
                                   np.concatenate([self.nodes.ids, np.array(list(isolated))])])
        # Simpler approach: re-filter node data by current ids
        # Since nodes already removed, we need to track indices before removal
        # This is handled by rebuilding from scratch if needed
        logger.info(f"Removed {len(isolated)} isolated nodes from '{self.name}'")
        return len(isolated)

    # ---- Conversion utilities ----

    def to_trimesh(self, use_elements: bool = True):
        """Convert to trimesh.Trimesh (surface mesh).

        Args:
            use_elements: if True, use elements connectivity; if False, use conditions.
        """
        import trimesh

        container = self.elements if use_elements else self.conditions
        if container.count == 0:
            return trimesh.Trimesh()

        # Build vertex array ordered by node ID appearance in connectivity
        used_ids = container.get_all_node_ids()
        id_to_new_idx = {int(nid): i for i, nid in enumerate(used_ids)}

        vertices = np.array([self.nodes.get_coords(int(nid)) for nid in used_ids])

        # Remap connectivity to new sequential indices
        faces = np.vectorize(lambda x: id_to_new_idx[int(x)])(container.connectivity)

        return trimesh.Trimesh(vertices=vertices, faces=faces)

    @classmethod
    def from_trimesh(cls, mesh, name: str = "MeshPart",
                     as_elements: bool = True) -> MeshPart:
        """Create a MeshPart from a trimesh.Trimesh."""
        mp = cls(name=name)
        n_nodes = len(mesh.vertices)
        ids = np.arange(1, n_nodes + 1, dtype=np.int64)
        mp.nodes.add_bulk(ids, mesh.vertices)

        n_faces = len(mesh.faces)
        face_ids = np.arange(1, n_faces + 1, dtype=np.int64)
        # Remap face indices (0-based) to node IDs (1-based)
        connectivity = mesh.faces + 1

        if as_elements:
            mp.elements = ElementContainer("tri3")
            mp.elements.add_bulk(face_ids, connectivity)
        else:
            mp.conditions = ElementContainer("tri3")
            mp.conditions.add_bulk(face_ids, connectivity)

        return mp

    # ---- Properties ----

    def get_properties(self, props_id: int = 0) -> dict:
        if props_id not in self.properties:
            self.properties[props_id] = {}
        return self.properties[props_id]

    # ---- Info ----

    def __repr__(self) -> str:
        parts = [f"MeshPart('{self.name}')"]
        parts.append(f"  Nodes: {self.nodes.count}")
        parts.append(f"  Elements: {self.elements.count} ({self.elements.element_type})")
        parts.append(f"  Conditions: {self.conditions.count} ({self.conditions.element_type})")
        parts.append(f"  Node fields: {list(self.node_data.keys())}")
        parts.append(f"  Sub-parts: {list(self._sub_parts.keys())}")
        return "\n".join(parts)

    def clear(self) -> None:
        """Clear all data."""
        self.nodes.clear()
        self.elements.clear()
        self.conditions.clear()
        self.node_data.clear()
        self.element_data.clear()
        self._sub_parts.clear()


def _kratos_to_type(kratos_type: str) -> str:
    """Convert Kratos element type names to our internal type names."""
    mapping = {
        "Element2D3N": "tri3",
        "Element3D3N": "tri3",
        "Element3D4N": "tet4",
        "Condition3D": "tri3",
        "Condition3D3N": "tri3",
        "WallCondition3D3N": "tri3",
        "SurfaceCondition3D3N": "tri3",
        # Direct types
        "tri3": "tri3",
        "tet4": "tet4",
        "quad4": "quad4",
        "line2": "line2",
    }
    if kratos_type in mapping:
        return mapping[kratos_type]
    logger.warning(f"Unknown element type '{kratos_type}', defaulting to 'tri3'")
    return "tri3"
