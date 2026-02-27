import asyncio

from dstack._internal.server.background.pipeline_tasks.base import Pipeline
from dstack._internal.server.background.pipeline_tasks.compute_groups import ComputeGroupPipeline
from dstack._internal.server.background.pipeline_tasks.fleets import FleetPipeline
from dstack._internal.server.background.pipeline_tasks.gateways import GatewayPipeline
from dstack._internal.server.background.pipeline_tasks.placement_groups import (
    PlacementGroupPipeline,
)
from dstack._internal.server.background.pipeline_tasks.volumes import VolumePipeline
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class PipelineManager:
    def __init__(self) -> None:
        self._pipelines: list[Pipeline] = [
            ComputeGroupPipeline(),
            FleetPipeline(),
            GatewayPipeline(),
            PlacementGroupPipeline(),
            VolumePipeline(),
        ]
        self._hinter = PipelineHinter(self._pipelines)

    def start(self):
        for pipeline in self._pipelines:
            pipeline.start()

    def shutdown(self):
        for pipeline in self._pipelines:
            pipeline.shutdown()

    async def drain(self):
        results = await asyncio.gather(
            *[p.drain() for p in self._pipelines], return_exceptions=True
        )
        for pipeline, result in zip(self._pipelines, results):
            if isinstance(result, BaseException):
                logger.error(
                    "Unexpected exception when draining pipeline %r",
                    pipeline,
                    exc_info=(type(result), result, result.__traceback__),
                )

    @property
    def hinter(self):
        return self._hinter


class PipelineHinter:
    def __init__(self, pipelines: list[Pipeline]) -> None:
        self._pipelines = pipelines
        self._hint_fetch_map = {p.hint_fetch_model_name: p for p in self._pipelines}

    def hint_fetch(self, model_name: str):
        pipeline = self._hint_fetch_map.get(model_name)
        if pipeline is None:
            logger.warning("Model %s not registered for fetch hints", model_name)
            return
        pipeline.hint_fetch()


def start_pipeline_tasks() -> PipelineManager:
    """
    Start tasks processed by fetch-workers pipelines based on db + in-memory queues.
    Suitable for tasks that run frequently and need to lock rows for a long time.
    """
    pipeline_manager = PipelineManager()
    pipeline_manager.start()
    return pipeline_manager
