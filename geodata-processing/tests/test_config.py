"""Tests for Pydantic configuration models."""

import json
import pytest

from geodata.config.settings import (
    ProjectSettings, DomainSettings, TerrainSettings, OutputSettings,
)


class TestProjectSettings:
    def test_defaults(self):
        settings = ProjectSettings()
        assert settings.project_name == "geodata_project"
        assert settings.domain.radius == 1000.0
        assert settings.buildings is None
        assert settings.cfd is None

    def test_json_roundtrip(self, tmp_path):
        settings = ProjectSettings(project_name="test_project")
        path = str(tmp_path / "settings.json")
        settings.to_json_file(path)

        loaded = ProjectSettings.from_json_file(path)
        assert loaded.project_name == "test_project"
        assert loaded.domain.radius == 1000.0

    def test_json_schema(self):
        schema = ProjectSettings.model_json_schema()
        assert "properties" in schema
        assert "project_name" in schema["properties"]

    def test_validation(self):
        with pytest.raises(Exception):
            DomainSettings(radius=-1)

    def test_output_formats(self):
        out = OutputSettings(formats=["stl", "obj", "gltf"])
        assert len(out.formats) == 3
