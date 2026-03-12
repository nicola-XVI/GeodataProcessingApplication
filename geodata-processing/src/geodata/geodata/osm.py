"""OpenStreetMap building download and processing.

Port of GeoData.DownloadBuildingsOSM and GeoData.GeoJSONtoOBJ:
download building footprints from Overpass API, extract heights,
merge overlapping polygons, triangulate, and extrude to 3D mesh.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from .coordinates import BoundingBox, haversine

logger = logging.getLogger(__name__)

# Default building height parameters
HEIGHT_PER_LEVEL = 3.0  # meters per building level
DEFAULT_HEIGHT = 9.0     # fallback height when no data available


def download_buildings_osm(
    bbox: BoundingBox,
    file_out: str,
    max_retries: int = 10,
    timeout: int = 60,
) -> dict:
    """Download buildings from OpenStreetMap via Overpass API.

    Port of GeoData.DownloadBuildingsOSM.

    Args:
        bbox: Geographic bounding box for the query.
        file_out: Output JSON file path.
        max_retries: Number of retry attempts on failure.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON dict with OSM elements.

    Raises:
        RuntimeError: If all retries fail.
    """
    import requests

    os.makedirs(os.path.dirname(file_out) or ".", exist_ok=True)

    # Ensure .json extension
    stem, ext = os.path.splitext(file_out)
    if ext.lower() != ".json":
        file_out = stem + ".json"

    # OSM bounding-box format: (south, west, north, east)
    osm_bbox = f"({bbox.south},{bbox.west},{bbox.north},{bbox.east})"

    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
        [out:json];
        (
            node{osm_bbox};
            way["building"]{osm_bbox};
            rel["building"]{osm_bbox};
        );
        out geom;
    """

    for attempt in range(max_retries):
        logger.info(f"Overpass API attempt {attempt + 1}/{max_retries}")
        try:
            response = requests.get(
                overpass_url,
                params={"data": overpass_query},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()

            with open(file_out, "w") as f:
                json.dump(data, f)

            n_elements = len(data.get("elements", []))
            logger.info(f"Downloaded {n_elements} OSM elements to {file_out}")
            return data

        except (json.JSONDecodeError, requests.RequestException) as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            continue

    raise RuntimeError(f"Failed to download OSM buildings after {max_retries} attempts")


def _parse_height_tag(value: str) -> Optional[float]:
    """Parse a height value from an OSM tag string."""
    try:
        cleaned = value.replace(" m", "").replace("m", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_levels_tag(value: str) -> Optional[int]:
    """Parse a levels value from an OSM tag string."""
    try:
        cleaned = value.replace(" m", "").strip()
        return int(cleaned)
    except (ValueError, TypeError):
        return None


def _extract_building_height(tags: dict) -> float:
    """Extract building height from OSM tags."""
    # Try direct height tags first
    for key in ("building:height", "height"):
        if key in tags:
            h = _parse_height_tag(tags[key])
            if h is not None and h > 0:
                return h

    # Try level-based height
    for key in ("building:levels", "level", "levels"):
        if key in tags:
            levels = _parse_levels_tag(tags[key])
            if levels is not None and levels > 0:
                return levels * HEIGHT_PER_LEVEL

    return DEFAULT_HEIGHT


def _extract_base_height(tags: dict) -> float:
    """Extract building base height (min_height) from OSM tags."""
    if "min_height" in tags:
        h = _parse_height_tag(tags["min_height"])
        if h is not None:
            return h
    return 0.0


def _extract_buildings_from_geojson(geojson: dict) -> list[dict]:
    """Extract building footprints and heights from Overpass JSON response.

    Returns list of dicts with keys: coords (list of (lon, lat) tuples),
    height (float), base_height (float).
    """
    buildings = []

    for element in geojson.get("elements", []):
        tags = element.get("tags", {})
        if "building" not in tags:
            continue

        height = _extract_building_height(tags)
        base_height = _extract_base_height(tags)

        coords: list[tuple[float, float]] = []

        # Way → "geometry" key
        if "geometry" in element:
            coords = [(g["lon"], g["lat"]) for g in element["geometry"]]

        # Relation (multipolygon) → "members" key, outer rings only
        elif "members" in element:
            coords = _merge_outer_rings(element["members"])

        if len(coords) >= 4:  # need at least 3 unique vertices + closing
            buildings.append({
                "coords": coords,
                "height": height,
                "base_height": base_height,
            })

    return buildings


def _merge_outer_rings(members: list[dict]) -> list[tuple[float, float]]:
    """Merge outer ring segments of a multipolygon relation.

    Port of the legacy multipolygon merging logic.
    """
    outer_segments: list[list[tuple[float, float]]] = []

    for member in members:
        if member.get("role") != "outer":
            continue
        segment = [(g["lon"], g["lat"]) for g in member.get("geometry", [])]
        if segment:
            outer_segments.append(segment)

    if not outer_segments:
        return []

    # Merge segments that share endpoints
    result = list(outer_segments[0])
    remaining = outer_segments[1:]

    changed = True
    while changed and remaining:
        changed = False
        for i, seg in enumerate(remaining):
            if result[-1] == seg[0]:
                result.extend(seg[1:])
                remaining.pop(i)
                changed = True
                break
            elif result[-1] == seg[-1]:
                result.extend(reversed(seg[:-1]))
                remaining.pop(i)
                changed = True
                break

    return result


def _merge_overlapping_buildings(buildings: list[dict]) -> list[dict]:
    """Merge overlapping building footprints using Shapely.

    Port of the legacy shapely union logic: intersecting buildings are
    merged, taking the max height and min base height.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    # Build polygon list
    polys = []
    for b in buildings:
        if len(b["coords"]) < 3:
            continue
        try:
            p = Polygon(b["coords"])
            if p.is_valid and not p.is_empty:
                polys.append({"poly": p, "height": b["height"],
                              "base_height": b["base_height"]})
        except Exception:
            continue

    # Iterative merge: check each polygon against all others
    merged = True
    while merged:
        merged = False
        i = 0
        while i < len(polys):
            j = i + 1
            while j < len(polys):
                if polys[i]["poly"].intersects(polys[j]["poly"]):
                    u = unary_union([polys[i]["poly"], polys[j]["poly"]])
                    if u.geom_type == "MultiPolygon":
                        # Only merge if intersection is more than a point
                        intersection = polys[i]["poly"].intersection(polys[j]["poly"])
                        if intersection.geom_type == "Point":
                            u = u.convex_hull
                        else:
                            j += 1
                            continue

                    new_entry = {
                        "poly": u,
                        "height": max(polys[i]["height"], polys[j]["height"]),
                        "base_height": min(polys[i]["base_height"], polys[j]["base_height"]),
                    }
                    polys[i] = new_entry
                    polys.pop(j)
                    merged = True
                else:
                    j += 1
            i += 1

    # Convert back to coordinate lists
    result = []
    for p in polys:
        coords = list(p["poly"].exterior.coords)
        result.append({
            "coords": coords,
            "height": p["height"],
            "base_height": p["base_height"],
        })

    return result


def geojson_to_mesh_parts(
    geojson: dict,
    reference_bbox: BoundingBox,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    merge_overlapping: bool = True,
) -> list[dict]:
    """Convert Overpass GeoJSON to 3D building mesh data.

    Port of GeoData.GeoJSONtoOBJ. Instead of writing OBJ directly,
    returns structured data suitable for creating MeshPart objects.

    Args:
        geojson: Parsed Overpass API JSON response.
        reference_bbox: Bounding box used for coordinate transformation
            (from DEM metadata: tl_x, br_y, scale_x, scale_y).
        scale_x: X scale factor (degrees to meters).
        scale_y: Y scale factor (degrees to meters).
        origin_x: X origin for coordinate translation (tl_x from DEM).
        origin_y: Y origin for coordinate translation (br_y from DEM).
        merge_overlapping: If True, merge overlapping building polygons.

    Returns:
        List of dicts, each with:
            - name: building name (str)
            - coords: (N, 3) array of vertex coordinates
            - faces: (M, 3) array of triangle connectivity (0-based)
            - height: building height (float)
            - base_height: building base height (float)
    """
    import triangle as tr

    buildings = _extract_buildings_from_geojson(geojson)
    logger.info(f"Extracted {len(buildings)} buildings from GeoJSON")

    if merge_overlapping and len(buildings) > 1:
        buildings = _merge_overlapping_buildings(buildings)
        logger.info(f"After merging: {len(buildings)} buildings")

    result = []
    for idx, b in enumerate(buildings):
        coords_2d = b["coords"]
        height = b["height"]
        base_height = b["base_height"]

        # Remove closing vertex if it duplicates the first
        if len(coords_2d) > 1 and coords_2d[0] == coords_2d[-1]:
            coords_2d = coords_2d[:-1]

        if len(coords_2d) < 3:
            continue

        # Triangulate the footprint using constrained Delaunay
        vertices = [(lon, lat) for lon, lat in coords_2d]
        n_verts = len(vertices)
        segments = [[i, (i + 1) % n_verts] for i in range(n_verts)]

        try:
            tri_input = dict(vertices=vertices, segments=segments)
            tri_result = tr.triangulate(tri_input, "p")
        except Exception as e:
            logger.warning(f"Triangulation failed for building {idx}: {e}")
            continue

        if "triangles" not in tri_result:
            logger.warning(f"No triangles for building {idx}, skipping")
            continue

        triangles = tri_result["triangles"]

        # Build 3D vertices: bottom (base_height) + top (height)
        n_bottom = len(coords_2d)
        all_coords = np.zeros((n_bottom * 2, 3), dtype=np.float64)

        for i, (lon, lat) in enumerate(coords_2d):
            x = (lon - origin_x) * scale_x
            y = (lat - origin_y) * scale_y
            all_coords[i] = [x, y, base_height]          # bottom
            all_coords[i + n_bottom] = [x, y, height]    # top

        # Build faces
        all_faces = []

        # Top faces (from triangulation, offset by n_bottom)
        for tri in triangles:
            all_faces.append([tri[0] + n_bottom, tri[1] + n_bottom, tri[2] + n_bottom])

        # Lateral faces (quads split into 2 triangles)
        for i in range(n_bottom):
            j = (i + 1) % n_bottom
            # Bottom-i, Bottom-j, Top-i
            all_faces.append([i, j, i + n_bottom])
            # Bottom-j, Top-j, Top-i
            all_faces.append([j, j + n_bottom, i + n_bottom])

        faces_array = np.array(all_faces, dtype=np.int64)

        result.append({
            "name": f"Building{idx + 1}",
            "coords": all_coords,
            "faces": faces_array,
            "height": height,
            "base_height": base_height,
        })

    logger.info(f"Created {len(result)} building meshes")
    return result


def geojson_to_obj(
    geojson: dict,
    file_out: str,
    reference_bbox: BoundingBox,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    merge_overlapping: bool = True,
) -> str:
    """Convert Overpass GeoJSON to OBJ file.

    Port of GeoData.GeoJSONtoOBJ.

    Args:
        geojson: Parsed Overpass API JSON response.
        file_out: Output OBJ file path.
        reference_bbox: Bounding box for coordinate transformation.
        scale_x, scale_y: Scale factors (degrees to meters).
        origin_x, origin_y: Origin for coordinate translation.
        merge_overlapping: If True, merge overlapping buildings.

    Returns:
        Path to the output OBJ file.
    """
    # Ensure .obj extension
    stem, ext = os.path.splitext(file_out)
    if ext.lower() != ".obj":
        file_out = stem + ".obj"

    mesh_parts = geojson_to_mesh_parts(
        geojson, reference_bbox,
        scale_x=scale_x, scale_y=scale_y,
        origin_x=origin_x, origin_y=origin_y,
        merge_overlapping=merge_overlapping,
    )

    lines = ["# Buildings from OpenStreetMap\n"]
    node_offset = 0

    for mp in mesh_parts:
        lines.append(f"\no {mp['name']}\n")

        for coord in mp["coords"]:
            lines.append(f"v {coord[0]:.10f} {coord[1]:.10f} {coord[2]:.6f}\n")

        for face in mp["faces"]:
            # OBJ is 1-based
            lines.append(f"f {face[0] + 1 + node_offset} "
                         f"{face[1] + 1 + node_offset} "
                         f"{face[2] + 1 + node_offset}\n")

        node_offset += len(mp["coords"])

    os.makedirs(os.path.dirname(file_out) or ".", exist_ok=True)
    with open(file_out, "w") as f:
        f.writelines(lines)

    logger.info(f"Wrote {len(mesh_parts)} buildings to {file_out}")
    return file_out


def buildings_to_mesh_part(
    geojson: dict,
    reference_bbox: BoundingBox,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    merge_overlapping: bool = True,
) -> "MeshPart":
    """Convert Overpass GeoJSON to a MeshPart with building sub-parts.

    Higher-level function that creates a full MeshPart hierarchy.

    Args:
        geojson: Parsed Overpass API JSON response.
        reference_bbox: Bounding box for coordinate transformation.
        scale_x, scale_y: Scale factors.
        origin_x, origin_y: Origin for coordinate translation.
        merge_overlapping: If True, merge overlapping buildings.

    Returns:
        MeshPart with one sub-part per building.
    """
    from ..core.mesh_part import MeshPart

    mesh_data = geojson_to_mesh_parts(
        geojson, reference_bbox,
        scale_x=scale_x, scale_y=scale_y,
        origin_x=origin_x, origin_y=origin_y,
        merge_overlapping=merge_overlapping,
    )

    buildings = MeshPart(name="Buildings")
    global_node_id = 1
    global_elem_id = 1

    for data in mesh_data:
        n_nodes = len(data["coords"])
        n_faces = len(data["faces"])

        node_ids = np.arange(global_node_id, global_node_id + n_nodes, dtype=np.int64)
        elem_ids = np.arange(global_elem_id, global_elem_id + n_faces, dtype=np.int64)

        # Remap face connectivity to global node IDs
        connectivity = data["faces"] + global_node_id  # 0-based local → 1-based global

        # Add to parent
        buildings.create_nodes_bulk(node_ids, data["coords"])
        buildings.create_elements_bulk("tri3", elem_ids, connectivity)

        # Create sub-part
        sp = buildings.create_sub_part(data["name"])
        sp.create_nodes_bulk(node_ids, data["coords"])
        sp.create_elements_bulk("tri3", elem_ids, connectivity)

        global_node_id += n_nodes
        global_elem_id += n_faces

    logger.info(f"Created MeshPart with {len(mesh_data)} building sub-parts, "
                f"{buildings.nodes.count} nodes, {buildings.elements.count} elements")
    return buildings
