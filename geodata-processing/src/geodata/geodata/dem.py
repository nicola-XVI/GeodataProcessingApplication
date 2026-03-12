"""DEM (Digital Elevation Model) download and processing.

Port of GeoData: download ASTER GDEM, crop to bounding box,
convert to mesh (OBJ or MeshPart).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from .coordinates import BoundingBox, haversine

logger = logging.getLogger(__name__)


def download_aster_gdem(
    output_dir: str,
    latitude: float,
    longitude: float,
    radius_m: float = 1000.0,
    username: str = "",
    password: str = "",
) -> str:
    """Download ASTER GDEM tiles from NASA EarthData.

    Port of GeoData.DownloadAsterGDEM.

    Requires a valid account at https://earthdata.nasa.gov/

    Args:
        output_dir: Directory where .tif files will be saved.
        latitude: Center latitude.
        longitude: Center longitude.
        radius_m: Search radius in meters (10 to 6,000,000).
        username: EarthData username.
        password: EarthData password.

    Returns:
        Path to the DEM file (single tile or merged mosaic).

    Raises:
        ValueError: If credentials are empty.
        RuntimeError: If download fails.
    """
    import requests

    if not username or not password:
        raise ValueError("EarthData username and password are required. "
                         "Register at https://earthdata.nasa.gov/")

    os.makedirs(output_dir, exist_ok=True)

    # Query NASA CMR API for ASTER GDEM v3 granules
    url = (
        "https://cmr.earthdata.nasa.gov/search/granules.json"
        f"?short_name=ASTGTM&version=003&page_size=2000&pageNum=1"
        f"&circle={longitude},{latitude},{radius_m}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    entries = response.json()["feed"]["entry"]

    if not entries:
        raise RuntimeError(f"No ASTER GDEM tiles found at ({latitude}, {longitude})")

    file_urls = [g["links"][0]["href"] for g in entries]
    downloaded_files = []

    for file_url in file_urls:
        name = file_url.split("/")[-1]
        out_path = os.path.join(output_dir, name)
        downloaded_files.append(out_path)

        if os.path.exists(out_path):
            logger.info(f"File already exists: {name}")
            continue

        with requests.Session() as session:
            r1 = session.get(file_url)
            r = session.get(r1.url, auth=(username, password))
            if r.ok:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"Downloaded: {name}")
            else:
                raise RuntimeError(f"Failed to download {name}: {r.status_code}")

    if len(downloaded_files) > 1:
        return _merge_rasters(downloaded_files, output_dir)

    return downloaded_files[0]


def _merge_rasters(file_paths: list[str], output_dir: str) -> str:
    """Merge multiple raster files into a single mosaic."""
    import rasterio
    from rasterio.merge import merge

    sources = [rasterio.open(fp) for fp in file_paths]
    mosaic, transform = merge(sources)

    out_meta = sources[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
    })

    for src in sources:
        src.close()

    merged_path = os.path.join(output_dir, "ASTER_GDEM_merged.tif")
    with rasterio.open(merged_path, "w", **out_meta) as dest:
        dest.write(mosaic)

    logger.info(f"Merged {len(file_paths)} tiles into {merged_path}")
    return merged_path


def crop_dem(
    file_in: str,
    bbox: BoundingBox,
    file_out: Optional[str] = None,
) -> str:
    """Crop a DEM raster to a bounding box.

    Port of GeoData.CropAsterGDEM.

    Args:
        file_in: Input DEM file path (.tif).
        bbox: Geographic bounding box for cropping.
        file_out: Output file path. If None, appends "_CROP" to input name.

    Returns:
        Path to the cropped DEM file.
    """
    import rasterio
    import rasterio.mask

    if file_out is None:
        stem, ext = os.path.splitext(file_in)
        file_out = f"{stem}_CROP{ext}"

    if bbox.west >= bbox.east or bbox.north <= bbox.south:
        raise ValueError(f"Invalid bbox: W={bbox.west} E={bbox.east} "
                         f"N={bbox.north} S={bbox.south}")

    geom = [{
        "type": "Polygon",
        "coordinates": [[
            [bbox.west, bbox.south],
            [bbox.east, bbox.south],
            [bbox.east, bbox.north],
            [bbox.west, bbox.north],
            [bbox.west, bbox.south],
        ]],
    }]

    with rasterio.open(file_in) as src:
        out_image, out_transform = rasterio.mask.mask(src, geom, crop=True)
        out_meta = src.meta.copy()

    out_meta.update({
        "driver": "GTiff",
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform,
    })

    with rasterio.open(file_out, "w", **out_meta) as dest:
        dest.write(out_image)

    logger.info(f"Cropped DEM to bbox: {out_image.shape[2]}x{out_image.shape[1]} pixels")
    return file_out


def dem_to_mesh_part(
    file_in: str,
    name: str = "Terrain",
) -> "MeshPart":
    """Convert a DEM raster to a MeshPart with triangulated surface.

    Port of GeoData.AsterGDEMtoOBJ but returns MeshPart directly.
    Coordinates are converted from geographic to local meters.

    Args:
        file_in: Input DEM file path (.tif).
        name: Name for the resulting MeshPart.

    Returns:
        MeshPart with terrain mesh (tri3 elements).
    """
    import rasterio

    from ..core.mesh_part import MeshPart

    with rasterio.open(file_in, "r") as src:
        transform = src.transform
        width, height = src.width, src.height
        data = src.read(1)  # elevation band

        # Geographic corners
        tl_x, tl_y = transform * (0, 0)
        br_x, br_y = transform * (width, height)

    # Compute scale factors (geographic degrees → meters)
    delta_x = haversine(tl_y, tl_x, tl_y, br_x)  # total width in meters
    delta_y = haversine(tl_y, tl_x, br_y, tl_x)  # total height in meters

    scale_x = delta_x / (br_x - tl_x) if abs(br_x - tl_x) > 1e-20 else 1.0
    scale_y = delta_y / (tl_y - br_y) if abs(tl_y - br_y) > 1e-20 else 1.0

    # Build node coordinates
    n_nodes = width * height
    coords = np.zeros((n_nodes, 3), dtype=np.float64)

    idx = 0
    for row in range(height):
        for col in range(width):
            geo_x, geo_y = transform * (col, row)
            x = (geo_x - tl_x) * scale_x
            y = (geo_y - br_y) * scale_y
            z = float(data[row, col])
            coords[idx] = [x, y, z]
            idx += 1

    node_ids = np.arange(1, n_nodes + 1, dtype=np.int64)

    # Build triangular connectivity (2 triangles per pixel)
    n_faces = (width - 1) * (height - 1) * 2
    connectivity = np.zeros((n_faces, 3), dtype=np.int64)

    face_idx = 0
    for row in range(height - 1):
        for col in range(width - 1):
            tl = 1 + row * width + col  # 1-based node ID
            tr = tl + 1
            bl = tl + width
            br = bl + 1
            connectivity[face_idx] = [tl, tr, bl]
            connectivity[face_idx + 1] = [tr, br, bl]
            face_idx += 2

    face_ids = np.arange(1, n_faces + 1, dtype=np.int64)

    mp = MeshPart(name=name)
    mp.create_nodes_bulk(node_ids, coords)
    mp.create_elements_bulk("tri3", face_ids, connectivity)

    logger.info(f"DEM to mesh: {n_nodes} nodes, {n_faces} elements "
                f"({width}x{height} pixels)")
    return mp


def dem_to_obj(
    file_in: str,
    file_out: Optional[str] = None,
) -> str:
    """Convert a DEM raster to an OBJ file.

    Port of GeoData.AsterGDEMtoOBJ.

    Args:
        file_in: Input DEM file path (.tif).
        file_out: Output OBJ path. If None, uses same name with .obj extension.

    Returns:
        Path to the OBJ file.
    """
    from ..io.writers import write_obj

    if file_out is None:
        file_out = str(Path(file_in).with_suffix(".obj"))

    mp = dem_to_mesh_part(file_in)
    write_obj(mp, file_out)

    logger.info(f"DEM converted to OBJ: {file_out}")
    return file_out
