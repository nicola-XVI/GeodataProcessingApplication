"""Geographic coordinate utilities.

Port of geo_data.py coordinate functions: bounding box computation,
Haversine distance, and lat/lon ↔ meters conversions.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# WGS-84 Earth radius in meters
EARTH_RADIUS_M = 6_378_137.0
EARTH_RADIUS_KM = EARTH_RADIUS_M / 1000.0


@dataclass
class BoundingBox:
    """Geographic bounding box in lat/lon."""
    north: float  # north latitude (max lat)
    south: float  # south latitude (min lat)
    east: float   # east longitude (max lon)
    west: float   # west longitude (min lon)

    @property
    def center_lat(self) -> float:
        return (self.north + self.south) / 2.0

    @property
    def center_lon(self) -> float:
        return (self.east + self.west) / 2.0

    @property
    def width_deg(self) -> float:
        """Width in degrees of longitude."""
        return self.east - self.west

    @property
    def height_deg(self) -> float:
        """Height in degrees of latitude."""
        return self.north - self.south

    def width_m(self) -> float:
        """Approximate width in meters at the center latitude."""
        return haversine(self.center_lat, self.west, self.center_lat, self.east)

    def height_m(self) -> float:
        """Approximate height in meters."""
        return haversine(self.south, self.center_lon, self.north, self.center_lon)

    def to_tuple(self) -> tuple[float, float, float, float]:
        """Return as (west, south, east, north) — standard OGC order."""
        return (self.west, self.south, self.east, self.north)

    def to_rasterio_window_args(self) -> dict:
        """Return as dict suitable for rasterio window reading."""
        return {
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
        }


def compute_bbox(
    lat_center: float,
    lon_center: float,
    radius_m: float,
) -> BoundingBox:
    """Compute a geographic bounding box from a center point and radius.

    Port of GeoData.ComputeBbox.

    Args:
        lat_center: Latitude of center point in degrees.
        lon_center: Longitude of center point in degrees.
        radius_m: Radius in meters.

    Returns:
        BoundingBox with north/south/east/west bounds.
    """
    lat_offset = math.degrees(radius_m / EARTH_RADIUS_M)
    lon_offset = math.degrees(
        radius_m / (EARTH_RADIUS_M * math.cos(math.radians(lat_center)))
    )

    north = lat_center + lat_offset
    south = lat_center - lat_offset
    east = lon_center + lon_offset
    west = lon_center - lon_offset

    bbox = BoundingBox(north=north, south=south, east=east, west=west)
    logger.info(f"Computed bbox: N={north:.6f} S={south:.6f} "
                f"E={east:.6f} W={west:.6f} (radius={radius_m}m)")
    return bbox


def haversine(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Compute great-circle distance between two geographic points.

    Port of GeoData._measure. Uses the Haversine formula.

    Args:
        lat1, lon1: First point in decimal degrees.
        lat2, lon2: Second point in decimal degrees.

    Returns:
        Distance in meters.
    """
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c * 1000.0  # meters


def latlon_to_meters(
    lat: float | np.ndarray,
    lon: float | np.ndarray,
    lat_ref: float,
    lon_ref: float,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Convert lat/lon to local meters relative to a reference point.

    Uses a simple equirectangular projection (accurate for small areas).

    Args:
        lat, lon: Coordinates to convert (scalar or array).
        lat_ref, lon_ref: Reference point (becomes origin).

    Returns:
        (x_meters, y_meters): Local Cartesian coordinates.
    """
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)

    cos_lat = math.cos(math.radians(lat_ref))
    x = (lon - lon_ref) * math.radians(1.0) * EARTH_RADIUS_M * cos_lat
    y = (lat - lat_ref) * math.radians(1.0) * EARTH_RADIUS_M

    return (float(x) if x.ndim == 0 else x,
            float(y) if y.ndim == 0 else y)


def meters_to_latlon(
    x: float | np.ndarray,
    y: float | np.ndarray,
    lat_ref: float,
    lon_ref: float,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Convert local meters back to lat/lon.

    Inverse of latlon_to_meters.

    Args:
        x, y: Local Cartesian coordinates in meters.
        lat_ref, lon_ref: Reference point (origin).

    Returns:
        (lat, lon): Geographic coordinates in degrees.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    cos_lat = math.cos(math.radians(lat_ref))
    lon = lon_ref + math.degrees(x / (EARTH_RADIUS_M * cos_lat))
    lat = lat_ref + math.degrees(y / EARTH_RADIUS_M)

    return (float(lat) if np.ndim(lat) == 0 else lat,
            float(lon) if np.ndim(lon) == 0 else lon)


def compute_pixel_size_m(
    lat: float,
    lon: float,
    delta_lat: float,
    delta_lon: float,
) -> tuple[float, float]:
    """Compute raster pixel size in meters from geographic pixel size.

    Port of GeoData._get_metadata delta_x/delta_y computation.

    Args:
        lat, lon: Center latitude/longitude of the raster.
        delta_lat: Pixel height in degrees.
        delta_lon: Pixel width in degrees.

    Returns:
        (dx_meters, dy_meters): Pixel size in meters.
    """
    dx = haversine(lat, lon, lat, lon + abs(delta_lon))
    dy = haversine(lat, lon, lat + abs(delta_lat), lon)
    return dx, dy
