"""Numpy-backed containers for nodes and elements.

These replace Kratos ModelPart's internal storage with efficient numpy arrays.
All spatial data is stored in contiguous arrays for vectorized operations.
"""

from __future__ import annotations

import numpy as np
from typing import Optional


class NodeContainer:
    """Stores mesh nodes with numpy-backed coordinate arrays.

    Nodes are stored as:
    - ids: int64 array of node IDs
    - coords: float64 array of shape (N, 3) for (x, y, z)
    - _id_to_index: dict for O(1) ID-to-array-index lookup
    """

    def __init__(self):
        self.ids: np.ndarray = np.empty(0, dtype=np.int64)
        self.coords: np.ndarray = np.empty((0, 3), dtype=np.float64)
        self._id_to_index: dict[int, int] = {}

    @property
    def count(self) -> int:
        return len(self.ids)

    def add(self, node_id: int, x: float, y: float, z: float) -> int:
        """Add a single node. Returns its array index."""
        if node_id in self._id_to_index:
            raise ValueError(f"Node ID {node_id} already exists")
        idx = self.count
        self.ids = np.append(self.ids, node_id)
        self.coords = np.vstack([self.coords, [[x, y, z]]]) if idx > 0 else np.array([[x, y, z]])
        self._id_to_index[node_id] = idx
        return idx

    def add_bulk(self, ids: np.ndarray, coords: np.ndarray) -> None:
        """Add multiple nodes at once (much faster than repeated add())."""
        if len(ids) == 0:
            return
        ids = np.asarray(ids, dtype=np.int64)
        coords = np.asarray(coords, dtype=np.float64).reshape(-1, 3)
        if len(ids) != len(coords):
            raise ValueError("ids and coords must have the same length")

        # Check for duplicate IDs
        duplicates = set(ids.tolist()) & set(self._id_to_index.keys())
        if duplicates:
            raise ValueError(f"Duplicate node IDs: {duplicates}")

        offset = self.count
        if offset == 0:
            self.ids = ids.copy()
            self.coords = coords.copy()
        else:
            self.ids = np.concatenate([self.ids, ids])
            self.coords = np.concatenate([self.coords, coords])

        for i, nid in enumerate(ids):
            self._id_to_index[int(nid)] = offset + i

    def get_index(self, node_id: int) -> int:
        """Get array index for a given node ID."""
        return self._id_to_index[node_id]

    def get_coords(self, node_id: int) -> np.ndarray:
        """Get (x, y, z) coordinates for a node ID."""
        return self.coords[self._id_to_index[node_id]]

    def has_node(self, node_id: int) -> bool:
        return node_id in self._id_to_index

    def remove_by_mask(self, keep_mask: np.ndarray) -> None:
        """Remove nodes where keep_mask is False. Rebuilds index."""
        keep_mask = np.asarray(keep_mask, dtype=bool)
        self.ids = self.ids[keep_mask]
        self.coords = self.coords[keep_mask]
        self._rebuild_index()

    def remove_by_ids(self, ids_to_remove: set[int]) -> None:
        """Remove nodes by their IDs."""
        if not ids_to_remove:
            return
        keep_mask = np.array([int(nid) not in ids_to_remove for nid in self.ids])
        self.remove_by_mask(keep_mask)

    def clear(self) -> None:
        self.ids = np.empty(0, dtype=np.int64)
        self.coords = np.empty((0, 3), dtype=np.float64)
        self._id_to_index.clear()

    def max_id(self) -> int:
        """Return the maximum node ID, or 0 if empty."""
        if self.count == 0:
            return 0
        return int(self.ids.max())

    def _rebuild_index(self) -> None:
        self._id_to_index = {int(nid): i for i, nid in enumerate(self.ids)}

    def __len__(self) -> int:
        return self.count

    def __contains__(self, node_id: int) -> bool:
        return self.has_node(node_id)

    def __iter__(self):
        """Iterate yielding (id, x, y, z) tuples."""
        for i in range(self.count):
            yield int(self.ids[i]), self.coords[i, 0], self.coords[i, 1], self.coords[i, 2]


class ElementContainer:
    """Stores mesh elements (triangles, tetrahedra, etc.) with numpy-backed arrays.

    Elements are stored as:
    - ids: int64 array of element IDs
    - connectivity: int64 array of shape (M, K) where K is nodes-per-element
    - element_type: string identifier ("tri3", "tet4", "quad4", etc.)
    - _id_to_index: dict for O(1) lookup
    """

    def __init__(self, element_type: str = "tri3"):
        self.ids: np.ndarray = np.empty(0, dtype=np.int64)
        self.connectivity: np.ndarray = np.empty((0, _nodes_per_type(element_type)), dtype=np.int64)
        self.element_type: str = element_type
        self._id_to_index: dict[int, int] = {}

    @property
    def count(self) -> int:
        return len(self.ids)

    @property
    def nodes_per_element(self) -> int:
        return _nodes_per_type(self.element_type)

    def add(self, elem_id: int, node_ids: list[int] | np.ndarray) -> int:
        """Add a single element. Returns its array index."""
        if elem_id in self._id_to_index:
            raise ValueError(f"Element ID {elem_id} already exists")
        node_ids = np.asarray(node_ids, dtype=np.int64)
        expected = self.nodes_per_element
        if len(node_ids) != expected:
            raise ValueError(f"Expected {expected} nodes for {self.element_type}, got {len(node_ids)}")

        idx = self.count
        self.ids = np.append(self.ids, elem_id)
        if idx == 0:
            self.connectivity = node_ids.reshape(1, -1)
        else:
            self.connectivity = np.vstack([self.connectivity, node_ids.reshape(1, -1)])
        self._id_to_index[elem_id] = idx
        return idx

    def add_bulk(self, ids: np.ndarray, connectivity: np.ndarray) -> None:
        """Add multiple elements at once."""
        if len(ids) == 0:
            return
        ids = np.asarray(ids, dtype=np.int64)
        connectivity = np.asarray(connectivity, dtype=np.int64)
        if connectivity.ndim == 1:
            connectivity = connectivity.reshape(-1, self.nodes_per_element)
        if len(ids) != len(connectivity):
            raise ValueError("ids and connectivity must have the same length")

        offset = self.count
        if offset == 0:
            self.ids = ids.copy()
            self.connectivity = connectivity.copy()
        else:
            self.ids = np.concatenate([self.ids, ids])
            self.connectivity = np.concatenate([self.connectivity, connectivity])

        for i, eid in enumerate(ids):
            self._id_to_index[int(eid)] = offset + i

    def get_node_ids(self, elem_id: int) -> np.ndarray:
        """Get the node IDs of an element."""
        return self.connectivity[self._id_to_index[elem_id]]

    def has_element(self, elem_id: int) -> bool:
        return elem_id in self._id_to_index

    def remove_by_mask(self, keep_mask: np.ndarray) -> None:
        """Remove elements where keep_mask is False."""
        keep_mask = np.asarray(keep_mask, dtype=bool)
        self.ids = self.ids[keep_mask]
        self.connectivity = self.connectivity[keep_mask]
        self._rebuild_index()

    def remove_by_ids(self, ids_to_remove: set[int]) -> None:
        """Remove elements by their IDs."""
        if not ids_to_remove:
            return
        keep_mask = np.array([int(eid) not in ids_to_remove for eid in self.ids])
        self.remove_by_mask(keep_mask)

    def get_all_node_ids(self) -> np.ndarray:
        """Return sorted unique node IDs referenced by all elements."""
        if self.count == 0:
            return np.empty(0, dtype=np.int64)
        return np.unique(self.connectivity)

    def clear(self) -> None:
        npn = self.nodes_per_element
        self.ids = np.empty(0, dtype=np.int64)
        self.connectivity = np.empty((0, npn), dtype=np.int64)
        self._id_to_index.clear()

    def max_id(self) -> int:
        if self.count == 0:
            return 0
        return int(self.ids.max())

    def _rebuild_index(self) -> None:
        self._id_to_index = {int(eid): i for i, eid in enumerate(self.ids)}

    def __len__(self) -> int:
        return self.count

    def __contains__(self, elem_id: int) -> bool:
        return self.has_element(elem_id)

    def __iter__(self):
        """Iterate yielding (id, node_ids_array) tuples."""
        for i in range(self.count):
            yield int(self.ids[i]), self.connectivity[i]


def _nodes_per_type(element_type: str) -> int:
    """Return the number of nodes for a given element type."""
    mapping = {
        "tri3": 3,       # 2D/3D triangle (Element2D3N, Element3D3N)
        "tet4": 4,       # 3D tetrahedron (Element3D4N)
        "quad4": 4,      # 2D/3D quadrilateral
        "hex8": 8,       # 3D hexahedron
        "line2": 2,      # Line segment
    }
    if element_type not in mapping:
        raise ValueError(f"Unknown element type: {element_type}. Supported: {list(mapping.keys())}")
    return mapping[element_type]
