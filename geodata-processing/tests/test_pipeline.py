"""Tests for pipeline modules: steps, runner, and cad_export."""

import os

import numpy as np
import pytest

from geodata.config.settings import ProjectSettings
from geodata.core.mesh_part import MeshPart


# ===========================================================================
# Helpers
# ===========================================================================

def _make_simple_terrain(tmp_path) -> str:
    """Create a simple STL terrain file for testing."""
    from geodata.io.writers import write_stl

    mp = MeshPart(name="Terrain")
    node_ids = np.array([1, 2, 3, 4], dtype=np.int64)
    coords = np.array([
        [0, 0, 0],
        [100, 0, 0],
        [100, 100, 5],
        [0, 100, 3],
    ], dtype=np.float64)
    mp.create_nodes_bulk(node_ids, coords)
    mp.create_elements_bulk("tri3",
                             np.array([1, 2], dtype=np.int64),
                             np.array([[1, 2, 3], [1, 3, 4]], dtype=np.int64))

    path = str(tmp_path / "terrain.stl")
    write_stl(mp, path)
    return path


# ===========================================================================
# io/cad_export.py tests
# ===========================================================================

class TestCadExport:
    def test_is_available(self):
        from geodata.io.cad_export import is_available

        # May or may not be installed; just check it doesn't crash
        result = is_available()
        assert isinstance(result, bool)

    def test_require_cadquery_raises_if_missing(self):
        from geodata.io.cad_export import is_available

        if not is_available():
            from geodata.io.cad_export import _require_cadquery
            with pytest.raises(ImportError, match="cadquery"):
                _require_cadquery()


# ===========================================================================
# pipeline/steps.py tests
# ===========================================================================

class TestPipelineContext:
    def test_creation(self):
        from geodata.pipeline.steps import PipelineContext

        settings = ProjectSettings()
        ctx = PipelineContext(settings=settings)
        assert ctx.terrain is None
        assert ctx.buildings is None
        assert len(ctx.step_log) == 0
        assert len(ctx.errors) == 0

    def test_log_step(self):
        from geodata.pipeline.steps import PipelineContext

        ctx = PipelineContext(settings=ProjectSettings())
        ctx.log_step("test", "hello")
        assert len(ctx.step_log) == 1
        assert "test" in ctx.step_log[0]


class TestLoadTerrainStep:
    def test_load_stl(self, tmp_path):
        from geodata.pipeline.steps import LoadTerrainStep, PipelineContext

        path = _make_simple_terrain(tmp_path)
        settings = ProjectSettings(
            terrain={"source": "stl", "file_path": path},
        )
        ctx = PipelineContext(settings=settings)
        step = LoadTerrainStep()
        step.run(ctx)

        assert ctx.terrain is not None
        assert ctx.terrain.nodes.count > 0

    def test_missing_file_errors(self):
        from geodata.pipeline.steps import LoadTerrainStep, PipelineContext

        settings = ProjectSettings(
            terrain={"source": "stl", "file_path": ""},
        )
        ctx = PipelineContext(settings=settings)
        step = LoadTerrainStep()
        step.run(ctx)

        assert ctx.terrain is None
        assert len(ctx.errors) > 0


class TestPreprocessTerrainStep:
    def test_shift(self, tmp_path):
        from geodata.pipeline.steps import (
            LoadTerrainStep,
            PipelineContext,
            PreprocessTerrainStep,
        )

        path = _make_simple_terrain(tmp_path)
        settings = ProjectSettings(
            terrain={"source": "stl", "file_path": path, "shift_to_origin": True},
        )
        ctx = PipelineContext(settings=settings)
        LoadTerrainStep().run(ctx)
        PreprocessTerrainStep().run(ctx)

        assert ctx.terrain is not None
        # After shift, centroid should be near origin
        centroid = ctx.terrain.nodes.coords.mean(axis=0)
        assert abs(centroid[0]) < 60
        assert abs(centroid[1]) < 60


class TestSetupCfdStep:
    def test_generates_json(self, tmp_path):
        from geodata.pipeline.steps import PipelineContext, SetupCfdStep

        settings = ProjectSettings(
            project_name="test_cfd",
            cfd={"enabled": True, "inlet_velocity": 10.0, "generate_json": True},
        )
        ctx = PipelineContext(settings=settings, output_dir=str(tmp_path))

        # Need a domain mesh for the step to proceed
        mp = MeshPart(name="domain")
        mp.create_nodes_bulk(np.array([1], dtype=np.int64),
                              np.array([[0, 0, 0]], dtype=np.float64))
        ctx.domain = mp

        step = SetupCfdStep()
        step.run(ctx)

        json_path = os.path.join(str(tmp_path), "ProjectParameters.json")
        assert os.path.exists(json_path)

    def test_skipped_when_disabled(self):
        from geodata.pipeline.steps import PipelineContext, SetupCfdStep

        settings = ProjectSettings(cfd=None)
        ctx = PipelineContext(settings=settings)
        SetupCfdStep().run(ctx)
        assert any("skipped" in s for s in ctx.step_log)


class TestExportStep:
    def test_export_obj(self, tmp_path):
        from geodata.pipeline.steps import ExportStep, PipelineContext

        settings = ProjectSettings(
            project_name="test_export",
            output={"formats": ["obj"], "output_directory": str(tmp_path)},
        )
        ctx = PipelineContext(settings=settings, output_dir=str(tmp_path))

        # Create a simple mesh as the domain
        mp = MeshPart(name="domain")
        mp.create_nodes_bulk(
            np.array([1, 2, 3], dtype=np.int64),
            np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        )
        mp.create_elements_bulk("tri3",
                                 np.array([1], dtype=np.int64),
                                 np.array([[1, 2, 3]], dtype=np.int64))
        ctx.domain = mp

        step = ExportStep()
        step.run(ctx)

        out_path = os.path.join(str(tmp_path), "test_export.obj")
        assert os.path.exists(out_path)
        assert ctx.final_mesh is not None


# ===========================================================================
# pipeline/runner.py tests
# ===========================================================================

class TestPipelineRunner:
    def test_runner_with_custom_steps(self):
        from geodata.pipeline.runner import PipelineRunner
        from geodata.pipeline.steps import PipelineStep, PipelineContext

        class DummyStep(PipelineStep):
            name = "dummy"
            def run(self, ctx: PipelineContext) -> None:
                ctx.log_step("dummy", "executed")

        settings = ProjectSettings()
        runner = PipelineRunner(settings, steps=[DummyStep()])
        ctx = runner.run()

        assert len(ctx.step_log) == 1
        assert "dummy" in ctx.step_log[0]
        assert len(ctx.errors) == 0

    def test_runner_stops_on_error(self):
        from geodata.pipeline.runner import PipelineRunner
        from geodata.pipeline.steps import PipelineStep, PipelineContext

        class FailStep(PipelineStep):
            name = "fail"
            def run(self, ctx: PipelineContext) -> None:
                raise RuntimeError("intentional failure")

        class NeverStep(PipelineStep):
            name = "never"
            def run(self, ctx: PipelineContext) -> None:
                ctx.log_step("never", "should not run")

        settings = ProjectSettings()
        runner = PipelineRunner(settings, steps=[FailStep(), NeverStep()])
        ctx = runner.run()

        assert len(ctx.errors) == 1
        assert "intentional failure" in ctx.errors[0]
        assert len(ctx.step_log) == 0  # NeverStep didn't run

    def test_run_step_by_name(self):
        from geodata.pipeline.runner import PipelineRunner
        from geodata.pipeline.steps import PipelineStep, PipelineContext

        class StepA(PipelineStep):
            name = "step_a"
            def run(self, ctx: PipelineContext) -> None:
                ctx.log_step("step_a")

        class StepB(PipelineStep):
            name = "step_b"
            def run(self, ctx: PipelineContext) -> None:
                ctx.log_step("step_b")

        settings = ProjectSettings()
        runner = PipelineRunner(settings, steps=[StepA(), StepB()])
        ctx = PipelineContext(settings=settings)
        runner.run_step("step_b", ctx)

        assert len(ctx.step_log) == 1
        assert "step_b" in ctx.step_log[0]

    def test_run_step_not_found(self):
        from geodata.pipeline.runner import PipelineRunner

        settings = ProjectSettings()
        runner = PipelineRunner(settings, steps=[])
        ctx = __import__("geodata.pipeline.steps", fromlist=["PipelineContext"]).PipelineContext(settings=settings)

        with pytest.raises(ValueError, match="not found"):
            runner.run_step("nonexistent", ctx)

    def test_terrain_only_pipeline(self, tmp_path):
        """Integration test: load terrain → preprocess → export."""
        from geodata.pipeline.runner import PipelineRunner
        from geodata.pipeline.steps import (
            ExportStep,
            LoadTerrainStep,
            PreprocessTerrainStep,
        )

        path = _make_simple_terrain(tmp_path)
        settings = ProjectSettings(
            project_name="terrain_test",
            terrain={"source": "stl", "file_path": path, "shift_to_origin": True},
            output={"formats": ["obj"], "output_directory": str(tmp_path / "out")},
        )

        runner = PipelineRunner(
            settings,
            steps=[LoadTerrainStep(), PreprocessTerrainStep(), ExportStep()],
            output_dir=str(tmp_path / "out"),
        )
        ctx = runner.run()

        assert len(ctx.errors) == 0
        assert ctx.final_mesh is not None
        assert os.path.exists(str(tmp_path / "out" / "terrain_test.obj"))


class TestConvenienceFunctions:
    def test_run_from_json(self, tmp_path):
        from geodata.pipeline.runner import PipelineRunner, run_from_json
        from geodata.pipeline.steps import PipelineStep, PipelineContext

        # Create a minimal config JSON
        settings = ProjectSettings(project_name="json_test")
        config_path = str(tmp_path / "config.json")
        settings.to_json_file(config_path)

        # run_from_json will fail at load_terrain (no file), but
        # it should at least parse config and start running
        ctx = run_from_json(config_path, output_dir=str(tmp_path))

        # Will have errors because no terrain file
        assert len(ctx.errors) > 0 or len(ctx.step_log) > 0
