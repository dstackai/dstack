import asyncio

from dstack._internal.server.background.pipeline_tasks.base import Pipeline
from dstack._internal.server.background.pipeline_tasks.compute_groups import ComputeGroupPipeline
from dstack._internal.server.background.pipeline_tasks.fleets import FleetPipeline
from dstack._internal.server.background.pipeline_tasks.gateways import GatewayPipeline
from dstack._internal.server.background.pipeline_tasks.instances import InstancePipeline
from dstack._internal.server.background.pipeline_tasks.jobs_running import JobRunningPipeline
from dstack._internal.server.background.pipeline_tasks.jobs_submitted import (
    JobSubmittedPipeline,
)
from dstack._internal.server.background.pipeline_tasks.jobs_terminating import (
    JobTerminatingPipeline,
)
from dstack._internal.server.background.pipeline_tasks.placement_groups import (
    PlacementGroupPipeline,
)
from dstack._internal.server.background.pipeline_tasks.runs import RunPipeline
from dstack._internal.server.background.pipeline_tasks.service_router_worker_sync import (
    ServiceRouterWorkerSyncPipeline,
)
from dstack._internal.server.background.pipeline_tasks.volumes import VolumePipeline
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class PipelineManager:
    def __init__(self) -> None:
        self._pipelines: list[Pipeline] = []
        self._hinter = PipelineHinter()
        for builtin_pipeline in [
            ComputeGroupPipeline(pipeline_hinter=self._hinter),
            FleetPipeline(pipeline_hinter=self._hinter),
            GatewayPipeline(pipeline_hinter=self._hinter),
            JobSubmittedPipeline(pipeline_hinter=self._hinter),
            JobRunningPipeline(pipeline_hinter=self._hinter),
            JobTerminatingPipeline(pipeline_hinter=self._hinter),
            InstancePipeline(pipeline_hinter=self._hinter),
            PlacementGroupPipeline(pipeline_hinter=self._hinter),
            RunPipeline(pipeline_hinter=self._hinter),
            ServiceRouterWorkerSyncPipeline(pipeline_hinter=self._hinter),
            VolumePipeline(pipeline_hinter=self._hinter),
        ]:
            self.register_pipeline(builtin_pipeline)

    def register_pipeline(self, pipeline: Pipeline):
        self._pipelines.append(pipeline)
        self._hinter.register_pipeline(pipeline)

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
    def __init__(self) -> None:
        self._hint_fetch_map: dict[str, list[Pipeline]] = {}

    def register_pipeline(self, pipeline: Pipeline):
        self._hint_fetch_map.setdefault(pipeline.hint_fetch_model_name, []).append(pipeline)

    def hint_fetch(self, model_name: str):
        pipelines = self._hint_fetch_map.get(model_name)
        if pipelines is None:
            logger.warning("Model %s not registered for fetch hints", model_name)
            return
        for pipeline in pipelines:
            pipeline.hint_fetch()


_pipeline_manager = PipelineManager()


def get_pipeline_manager() -> PipelineManager:
    return _pipeline_manager


def start_pipeline_tasks() -> PipelineManager:
    """
    Start tasks processed by fetch-workers pipelines based on db + in-memory queues.
    Suitable for tasks that run frequently and need to lock rows for a long time.
    """
    _pipeline_manager.start()
    return _pipeline_manager
