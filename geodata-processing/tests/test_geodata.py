"""Tests for geodata modules: coordinates, dem, osm."""

import math
import os
import tempfile

import numpy as np
import pytest

from geodata.geodata.coordinates import (
    EARTH_RADIUS_M,
    BoundingBox,
    compute_bbox,
    compute_pixel_size_m,
    haversine,
    latlon_to_meters,
    meters_to_latlon,
)


# ===========================================================================
# coordinates.py tests
# ===========================================================================

class TestBoundingBox:
    def test_basic_properties(self):
        bbox = BoundingBox(north=42.0, south=41.0, east=14.0, west=13.0)
        assert bbox.center_lat == pytest.approx(41.5)
        assert bbox.center_lon == pytest.approx(13.5)
        assert bbox.width_deg == pytest.approx(1.0)
        assert bbox.height_deg == pytest.approx(1.0)

    def test_to_tuple(self):
        bbox = BoundingBox(north=42.0, south=41.0, east=14.0, west=13.0)
        assert bbox.to_tuple() == (13.0, 41.0, 14.0, 42.0)

    def test_width_height_meters(self):
        bbox = BoundingBox(north=42.01, south=41.99, east=14.01, west=13.99)
        w = bbox.width_m()
        h = bbox.height_m()
        assert w > 0
        assert h > 0
        # ~0.02 degrees ≈ ~2.2 km lat, ~1.6 km lon at lat 42
        assert 1000 < w < 3000
        assert 1000 < h < 3000


class TestComputeBbox:
    def test_basic(self):
        bbox = compute_bbox(42.0, 14.0, 1000.0)
        assert bbox.north > 42.0
        assert bbox.south < 42.0
        assert bbox.east > 14.0
        assert bbox.west < 14.0

    def test_symmetry(self):
        bbox = compute_bbox(0.0, 0.0, 5000.0)
        assert bbox.north == pytest.approx(-bbox.south, abs=1e-6)
        assert bbox.east == pytest.approx(-bbox.west, abs=1e-6)

    def test_larger_radius_larger_bbox(self):
        small = compute_bbox(42.0, 14.0, 500.0)
        large = compute_bbox(42.0, 14.0, 5000.0)
        assert large.north > small.north
        assert large.east > small.east


class TestHaversine:
    def test_same_point(self):
        d = haversine(42.0, 14.0, 42.0, 14.0)
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_known_distance(self):
        # Rome (41.9, 12.5) to Naples (40.85, 14.27) ≈ 190 km
        d = haversine(41.9, 12.5, 40.85, 14.27)
        assert 180_000 < d < 200_000

    def test_one_degree_latitude(self):
        # 1 degree latitude ≈ 111 km
        d = haversine(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000

    def test_symmetry(self):
        d1 = haversine(42.0, 14.0, 43.0, 15.0)
        d2 = haversine(43.0, 15.0, 42.0, 14.0)
        assert d1 == pytest.approx(d2, rel=1e-10)


class TestLatlonMeters:
    def test_origin_is_zero(self):
        x, y = latlon_to_meters(42.0, 14.0, 42.0, 14.0)
        assert x == pytest.approx(0.0, abs=1e-6)
        assert y == pytest.approx(0.0, abs=1e-6)

    def test_roundtrip(self):
        lat, lon = 42.35, 14.17
        lat_ref, lon_ref = 42.0, 14.0
        x, y = latlon_to_meters(lat, lon, lat_ref, lon_ref)
        lat2, lon2 = meters_to_latlon(x, y, lat_ref, lon_ref)
        assert lat2 == pytest.approx(lat, abs=1e-6)
        assert lon2 == pytest.approx(lon, abs=1e-6)

    def test_array_input(self):
        lats = np.array([42.0, 42.1, 42.2])
        lons = np.array([14.0, 14.1, 14.2])
        xs, ys = latlon_to_meters(lats, lons, 42.0, 14.0)
        assert isinstance(xs, np.ndarray)
        assert len(xs) == 3
        assert xs[0] == pytest.approx(0.0, abs=1e-3)


class TestComputePixelSize:
    def test_basic(self):
        dx, dy = compute_pixel_size_m(42.0, 14.0, 1.0 / 3600, 1.0 / 3600)
        # 1 arcsecond ≈ 30 m
        assert 20 < dx < 40
        assert 25 < dy < 35


# ===========================================================================
# dem.py tests (no rasterio dependency needed for logic tests)
# ===========================================================================

class TestDemToMeshPart:
    """Test DEM-to-mesh conversion using a synthetic raster."""

    @pytest.fixture
    def synthetic_dem(self, tmp_path):
        """Create a small synthetic GeoTIFF."""
        rasterio = pytest.importorskip("rasterio")
        from rasterio.transform import from_bounds

        width, height = 5, 4
        data = np.arange(width * height, dtype=np.float32).reshape(height, width)
        # Place near equator for simpler math
        transform = from_bounds(14.0, 42.0, 14.01, 42.01, width, height)

        path = str(tmp_path / "test_dem.tif")
        with rasterio.open(
            path, "w", driver="GTiff",
            height=height, width=width, count=1,
            dtype="float32", transform=transform,
            crs="EPSG:4326",
        ) as dst:
            dst.write(data, 1)
        return path

    def test_mesh_part_shape(self, synthetic_dem):
        from geodata.geodata.dem import dem_to_mesh_part

        mp = dem_to_mesh_part(synthetic_dem)
        # 5x4 = 20 nodes, (5-1)*(4-1)*2 = 24 triangles
        assert mp.nodes.count == 20
        assert mp.elements.count == 24

    def test_mesh_part_name(self, synthetic_dem):
        from geodata.geodata.dem import dem_to_mesh_part

        mp = dem_to_mesh_part(synthetic_dem, name="MyTerrain")
        assert mp.name == "MyTerrain"


class TestCropDem:
    @pytest.fixture
    def synthetic_dem(self, tmp_path):
        rasterio = pytest.importorskip("rasterio")
        from rasterio.transform import from_bounds

        width, height = 10, 10
        data = np.ones((height, width), dtype=np.float32) * 100.0
        transform = from_bounds(13.0, 41.0, 15.0, 43.0, width, height)

        path = str(tmp_path / "big_dem.tif")
        with rasterio.open(
            path, "w", driver="GTiff",
            height=height, width=width, count=1,
            dtype="float32", transform=transform,
            crs="EPSG:4326",
        ) as dst:
            dst.write(data, 1)
        return path

    def test_crop_reduces_size(self, synthetic_dem, tmp_path):
        rasterio = pytest.importorskip("rasterio")
        from geodata.geodata.dem import crop_dem

        crop_bbox = BoundingBox(north=42.5, south=41.5, east=14.5, west=13.5)
        out_path = str(tmp_path / "cropped.tif")
        result = crop_dem(synthetic_dem, crop_bbox, out_path)

        with rasterio.open(result) as src:
            assert src.width <= 10
            assert src.height <= 10

    def test_crop_invalid_bbox_raises(self, synthetic_dem):
        from geodata.geodata.dem import crop_dem

        bad_bbox = BoundingBox(north=41.0, south=42.0, east=14.0, west=13.0)
        with pytest.raises(ValueError):
            crop_dem(synthetic_dem, bad_bbox)


class TestDemToObj:
    @pytest.fixture
    def synthetic_dem(self, tmp_path):
        rasterio = pytest.importorskip("rasterio")
        from rasterio.transform import from_bounds

        width, height = 3, 3
        data = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.float32)
        transform = from_bounds(14.0, 42.0, 14.01, 42.01, width, height)

        path = str(tmp_path / "small_dem.tif")
        with rasterio.open(
            path, "w", driver="GTiff",
            height=height, width=width, count=1,
            dtype="float32", transform=transform,
            crs="EPSG:4326",
        ) as dst:
            dst.write(data, 1)
        return path

    def test_creates_obj_file(self, synthetic_dem, tmp_path):
        from geodata.geodata.dem import dem_to_obj

        out = str(tmp_path / "out.obj")
        result = dem_to_obj(synthetic_dem, out)
        assert os.path.exists(result)
        assert result.endswith(".obj")

        content = open(result).read()
        assert "v " in content
        assert "f " in content


# ===========================================================================
# osm.py tests
# ===========================================================================

class TestExtractBuildings:
    def test_extract_way_building(self):
        from geodata.geodata.osm import _extract_buildings_from_geojson

        geojson = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes", "height": "12"},
                    "geometry": [
                        {"lon": 14.0, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.0},
                    ],
                }
            ]
        }
        buildings = _extract_buildings_from_geojson(geojson)
        assert len(buildings) == 1
        assert buildings[0]["height"] == pytest.approx(12.0)
        assert len(buildings[0]["coords"]) == 5

    def test_extract_levels(self):
        from geodata.geodata.osm import _extract_buildings_from_geojson

        geojson = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes", "building:levels": "4"},
                    "geometry": [
                        {"lon": 14.0, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.0},
                    ],
                }
            ]
        }
        buildings = _extract_buildings_from_geojson(geojson)
        assert buildings[0]["height"] == pytest.approx(12.0)  # 4 * 3.0

    def test_default_height(self):
        from geodata.geodata.osm import _extract_buildings_from_geojson

        geojson = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes"},
                    "geometry": [
                        {"lon": 14.0, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.0},
                    ],
                }
            ]
        }
        buildings = _extract_buildings_from_geojson(geojson)
        assert buildings[0]["height"] == pytest.approx(9.0)  # default

    def test_skip_non_building(self):
        from geodata.geodata.osm import _extract_buildings_from_geojson

        geojson = {
            "elements": [
                {
                    "type": "node",
                    "tags": {"amenity": "cafe"},
                }
            ]
        }
        buildings = _extract_buildings_from_geojson(geojson)
        assert len(buildings) == 0


class TestGeojsonToMeshParts:
    def _make_geojson(self, n_buildings=1):
        """Create a simple geojson with square buildings."""
        elements = []
        for i in range(n_buildings):
            offset = i * 0.005
            elements.append({
                "type": "way",
                "tags": {"building": "yes", "height": str(10 + i * 5)},
                "geometry": [
                    {"lon": 14.0 + offset, "lat": 42.0},
                    {"lon": 14.002 + offset, "lat": 42.0},
                    {"lon": 14.002 + offset, "lat": 42.002},
                    {"lon": 14.0 + offset, "lat": 42.002},
                    {"lon": 14.0 + offset, "lat": 42.0},
                ],
            })
        return {"elements": elements}

    def test_single_building(self):
        from geodata.geodata.osm import geojson_to_mesh_parts

        bbox = BoundingBox(north=42.01, south=42.0, east=14.01, west=14.0)
        parts = geojson_to_mesh_parts(
            self._make_geojson(1), bbox,
            scale_x=1.0, scale_y=1.0,
            origin_x=14.0, origin_y=42.0,
        )
        assert len(parts) == 1
        assert parts[0]["name"] == "Building1"
        assert parts[0]["height"] == pytest.approx(10.0)
        # 4 bottom + 4 top = 8 vertices
        assert len(parts[0]["coords"]) == 8
        # 2 top triangles + 4*2 lateral triangles = 10
        assert len(parts[0]["faces"]) == 10

    def test_multiple_buildings(self):
        from geodata.geodata.osm import geojson_to_mesh_parts

        bbox = BoundingBox(north=42.01, south=42.0, east=14.02, west=14.0)
        parts = geojson_to_mesh_parts(
            self._make_geojson(3), bbox,
            scale_x=1.0, scale_y=1.0,
            origin_x=14.0, origin_y=42.0,
            merge_overlapping=False,
        )
        assert len(parts) == 3

    def test_coords_are_transformed(self):
        from geodata.geodata.osm import geojson_to_mesh_parts

        bbox = BoundingBox(north=42.01, south=42.0, east=14.01, west=14.0)
        parts = geojson_to_mesh_parts(
            self._make_geojson(1), bbox,
            scale_x=100000.0, scale_y=100000.0,
            origin_x=14.0, origin_y=42.0,
        )
        coords = parts[0]["coords"]
        # Origin should be at (0, 0), and scaling should apply
        assert coords[0, 0] == pytest.approx(0.0, abs=1e-3)
        assert coords[0, 1] == pytest.approx(0.0, abs=1e-3)
        # Second vertex at lon=14.002, so (14.002-14.0)*100000 = 200
        assert coords[1, 0] == pytest.approx(200.0, abs=1e-3)


class TestBuildingsToMeshPart:
    def test_creates_mesh_part_with_subparts(self):
        from geodata.geodata.osm import buildings_to_mesh_part

        geojson = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes", "height": "10"},
                    "geometry": [
                        {"lon": 14.0, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.0},
                    ],
                }
            ]
        }
        bbox = BoundingBox(north=42.01, south=42.0, east=14.01, west=14.0)
        mp = buildings_to_mesh_part(geojson, bbox)
        assert mp.nodes.count == 8
        assert mp.elements.count == 10
        assert "Building1" in mp.sub_parts


class TestGeojsonToObj:
    def test_writes_obj_file(self, tmp_path):
        from geodata.geodata.osm import geojson_to_obj

        geojson = {
            "elements": [
                {
                    "type": "way",
                    "tags": {"building": "yes"},
                    "geometry": [
                        {"lon": 14.0, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.0},
                        {"lon": 14.001, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.001},
                        {"lon": 14.0, "lat": 42.0},
                    ],
                }
            ]
        }
        bbox = BoundingBox(north=42.01, south=42.0, east=14.01, west=14.0)
        out = str(tmp_path / "buildings.obj")
        result = geojson_to_obj(geojson, out, bbox)

        assert os.path.exists(result)
        content = open(result).read()
        assert "o Building1" in content
        assert "v " in content
        assert "f " in content


class TestMergeOverlapping:
    def test_overlapping_buildings_merged(self):
        from geodata.geodata.osm import _merge_overlapping_buildings

        b1 = {
            "coords": [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)],
            "height": 10.0,
            "base_height": 0.0,
        }
        b2 = {
            "coords": [(1, 0), (3, 0), (3, 2), (1, 2), (1, 0)],
            "height": 15.0,
            "base_height": 0.0,
        }
        result = _merge_overlapping_buildings([b1, b2])
        assert len(result) == 1
        assert result[0]["height"] == pytest.approx(15.0)

    def test_non_overlapping_stay_separate(self):
        from geodata.geodata.osm import _merge_overlapping_buildings

        b1 = {
            "coords": [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)],
            "height": 10.0,
            "base_height": 0.0,
        }
        b2 = {
            "coords": [(5, 5), (6, 5), (6, 6), (5, 6), (5, 5)],
            "height": 10.0,
            "base_height": 0.0,
        }
        result = _merge_overlapping_buildings([b1, b2])
        assert len(result) == 2


class TestParseHeightTags:
    def test_parse_height(self):
        from geodata.geodata.osm import _parse_height_tag

        assert _parse_height_tag("12") == pytest.approx(12.0)
        assert _parse_height_tag("12 m") == pytest.approx(12.0)
        assert _parse_height_tag("12m") == pytest.approx(12.0)
        assert _parse_height_tag("abc") is None

    def test_parse_levels(self):
        from geodata.geodata.osm import _parse_levels_tag

        assert _parse_levels_tag("4") == 4
        assert _parse_levels_tag("abc") is None
