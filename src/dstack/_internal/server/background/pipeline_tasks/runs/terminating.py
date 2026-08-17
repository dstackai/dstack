import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server import models
from dstack._internal.server.background.pipeline_tasks.base import ItemUpdateMap
from dstack._internal.server.services.runs import _get_next_triggered_at, get_run_spec
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class TerminatingRunUpdateMap(ItemUpdateMap, total=False):
    status: RunStatus
    next_triggered_at: Optional[datetime]
    fleet_id: Optional[uuid.UUID]
    resubmission_attempt: int


class TerminatingRunJobUpdateMap(ItemUpdateMap, total=False):
    status: JobStatus
    termination_reason: Optional[JobTerminationReason]
    graceful_termination_attempts: int
    skip_min_processing_interval: bool


@dataclass
class TerminatingContext:
    run_model: models.RunModel
    locked_job_ids: set[uuid.UUID]


@dataclass
class TerminatingResult:
    run_update_map: TerminatingRunUpdateMap = field(default_factory=TerminatingRunUpdateMap)
    job_id_to_update_map: dict[uuid.UUID, TerminatingRunJobUpdateMap] = field(default_factory=dict)


async def process_terminating_run(context: TerminatingContext) -> TerminatingResult:
    """
    Stops the jobs gracefully and marks them as TERMINATING.
    Jobs then should be terminated by `JobTerminatingPipeline`.
    When all jobs are already terminated, assigns a finished status to the run.
    Caller must preload the run, acquire related job locks, and apply the result.
    """
    run_model = context.run_model
    assert run_model.termination_reason is not None

    job_termination_reason = run_model.termination_reason.to_job_termination_reason()
    if len(context.locked_job_ids) > 0:
        locked_jobs = [j for j in run_model.jobs if j.id in context.locked_job_ids]
        delayed_job_ids = []
        regular_job_ids = []
        for job_model in locked_jobs:
            if job_model.status == JobStatus.RUNNING and job_termination_reason not in {
                JobTerminationReason.ABORTED_BY_USER,
                JobTerminationReason.DONE_BY_RUNNER,
            }:
                delayed_job_ids.append(job_model.id)
                continue
            regular_job_ids.append(job_model.id)
        return TerminatingResult(
            job_id_to_update_map=_get_job_id_to_update_map(
                delayed_job_ids=delayed_job_ids,
                regular_job_ids=regular_job_ids,
                job_termination_reason=job_termination_reason,
            )
        )

    if any(not job_model.status.is_finished() for job_model in run_model.jobs):
        return TerminatingResult()

    return TerminatingResult(
        run_update_map=_get_run_update_map(run_model),
    )


def _get_job_id_to_update_map(
    delayed_job_ids: list[uuid.UUID],
    regular_job_ids: list[uuid.UUID],
    job_termination_reason: JobTerminationReason,
) -> dict[uuid.UUID, TerminatingRunJobUpdateMap]:
    job_id_to_update_map = {}
    for job_id in regular_job_ids:
        job_id_to_update_map[job_id] = TerminatingRunJobUpdateMap(
            status=JobStatus.TERMINATING,
            termination_reason=job_termination_reason,
            skip_min_processing_interval=True,
        )
    for job_id in delayed_job_ids:
        job_id_to_update_map[job_id] = TerminatingRunJobUpdateMap(
            status=JobStatus.TERMINATING,
            termination_reason=job_termination_reason,
            graceful_termination_attempts=0,
            skip_min_processing_interval=True,
        )
    return job_id_to_update_map


def _get_run_update_map(run_model: models.RunModel) -> TerminatingRunUpdateMap:
    termination_reason = get_or_error(run_model.termination_reason)
    run_spec = get_run_spec(run_model)
    if run_spec.merged_profile.schedule is not None and termination_reason not in {
        RunTerminationReason.ABORTED_BY_USER,
        RunTerminationReason.STOPPED_BY_USER,
    }:
        return TerminatingRunUpdateMap(
            status=RunStatus.PENDING,
            next_triggered_at=_get_next_triggered_at(run_spec),
            fleet_id=None,
            resubmission_attempt=0,
        )
    return TerminatingRunUpdateMap(status=termination_reason.to_status())
