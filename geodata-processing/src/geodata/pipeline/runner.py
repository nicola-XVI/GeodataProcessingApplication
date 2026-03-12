"""Pipeline runner: orchestrates the full geodata processing workflow.

Port of test_application.py workflow into a configurable, step-based
pipeline that can be run programmatically or from CLI.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ..config.settings import ProjectSettings
from .steps import (
    CleanMeshStep,
    CreateDomainStep,
    ExportStep,
    LoadBuildingsStep,
    LoadTerrainStep,
    PipelineContext,
    PipelineStep,
    PlaceBuildingsStep,
    PreprocessTerrainStep,
    RefineMeshStep,
    SetupCfdStep,
    SubtractBuildingsStep,
)

logger = logging.getLogger(__name__)


# Default pipeline step sequence
DEFAULT_STEPS: list[type[PipelineStep]] = [
    LoadTerrainStep,
    PreprocessTerrainStep,
    CreateDomainStep,
    LoadBuildingsStep,
    PlaceBuildingsStep,
    SubtractBuildingsStep,
    RefineMeshStep,
    CleanMeshStep,
    SetupCfdStep,
    ExportStep,
]


class PipelineRunner:
    """Orchestrates the geodata processing pipeline.

    Executes a sequence of PipelineStep instances, passing a shared
    PipelineContext between them.

    Usage:
        settings = ProjectSettings.from_json_file("config.json")
        runner = PipelineRunner(settings)
        ctx = runner.run()
    """

    def __init__(
        self,
        settings: ProjectSettings,
        steps: Optional[list[PipelineStep]] = None,
        output_dir: Optional[str] = None,
    ):
        """Initialize the pipeline.

        Args:
            settings: Project configuration.
            steps: Custom step sequence. If None, uses DEFAULT_STEPS.
            output_dir: Override output directory.
        """
        self.settings = settings
        self.steps = steps or [cls() for cls in DEFAULT_STEPS]
        self.output_dir = output_dir or settings.output.output_directory

    def run(self) -> PipelineContext:
        """Execute all pipeline steps in order.

        Returns:
            PipelineContext with results and logs.
        """
        ctx = PipelineContext(
            settings=self.settings,
            output_dir=self.output_dir,
        )

        logger.info(f"Starting pipeline: {self.settings.project_name}")
        t_start = time.time()

        for step in self.steps:
            step_name = getattr(step, "name", step.__class__.__name__)
            logger.info(f"Running step: {step_name}")
            t_step = time.time()

            try:
                step.run(ctx)
            except Exception as e:
                msg = f"Step '{step_name}' failed: {e}"
                logger.error(msg)
                ctx.errors.append(msg)
                break

            dt = time.time() - t_step
            logger.info(f"Step '{step_name}' completed in {dt:.2f}s")

        dt_total = time.time() - t_start
        logger.info(f"Pipeline completed in {dt_total:.2f}s "
                    f"({len(ctx.step_log)} steps, {len(ctx.errors)} errors)")

        return ctx

    def run_step(self, step_name: str, ctx: PipelineContext) -> PipelineContext:
        """Run a single step by name.

        Args:
            step_name: Name of the step to run.
            ctx: Existing pipeline context.

        Returns:
            Updated context.
        """
        for step in self.steps:
            if getattr(step, "name", "") == step_name:
                step.run(ctx)
                return ctx

        raise ValueError(f"Step '{step_name}' not found in pipeline")


def run_pipeline(
    settings: ProjectSettings,
    output_dir: Optional[str] = None,
) -> PipelineContext:
    """Convenience function to run the full pipeline.

    Args:
        settings: Project configuration.
        output_dir: Override output directory.

    Returns:
        PipelineContext with results.
    """
    runner = PipelineRunner(settings, output_dir=output_dir)
    return runner.run()


def run_from_json(config_path: str, output_dir: Optional[str] = None) -> PipelineContext:
    """Run the pipeline from a JSON configuration file.

    Args:
        config_path: Path to project settings JSON.
        output_dir: Override output directory.

    Returns:
        PipelineContext with results.
    """
    settings = ProjectSettings.from_json_file(config_path)
    return run_pipeline(settings, output_dir=output_dir)
