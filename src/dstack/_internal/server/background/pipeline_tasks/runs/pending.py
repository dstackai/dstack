"""Pending-run processing helpers for the run pipeline."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from dstack._internal.core.models.runs import RunSpec, RunStatus
from dstack._internal.server.background.pipeline_tasks.base import ItemUpdateMap
from dstack._internal.server.background.pipeline_tasks.runs.common import (
    build_scale_up_job_models,
)
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class PendingRunUpdateMap(ItemUpdateMap, total=False):
    status: RunStatus
    desired_replica_count: int


@dataclass
class PendingContext:
    run_model: RunModel
    run_spec: RunSpec
    secrets: dict
    locked_job_ids: list[uuid.UUID]


@dataclass
class PendingResult:
    run_update_map: PendingRunUpdateMap
    new_job_models: list[JobModel]


async def process_pending_run(context: PendingContext) -> Optional[PendingResult]:
    """
    Returns None if the run is not ready for processing (retry delay not met,
    zero-scaled service, etc.). Otherwise returns a result describing the
    desired state change and pre-built job models.
    """
    run_model = context.run_model
    run_spec = context.run_spec

    if run_model.resubmission_attempt > 0 and not _is_ready_for_resubmission(run_model):
        return None

    if run_spec.configuration.type == "service":
        logger.debug(
            "Skipping service run %s: pending service path not yet implemented", run_model.id
        )
        return None

    desired_replica_count = 1
    new_job_models = await build_scale_up_job_models(
        run_model=run_model,
        run_spec=run_spec,
        secrets=context.secrets,
        replicas_diff=desired_replica_count,
    )
    return PendingResult(
        run_update_map=PendingRunUpdateMap(
            status=RunStatus.SUBMITTED,
            desired_replica_count=desired_replica_count,
        ),
        new_job_models=new_job_models,
    )


def _is_ready_for_resubmission(run_model: RunModel) -> bool:
    if not run_model.jobs:
        # No jobs yet — should not be possible for resubmission, but allow processing.
        return True
    last_processed_at = max(job.last_processed_at for job in run_model.jobs)
    duration_since_processing = get_current_datetime() - last_processed_at
    return duration_since_processing >= _get_retry_delay(run_model.resubmission_attempt)


# We use exponentially increasing retry delays for pending runs.
# This prevents creation of too many job submissions for runs stuck in pending,
# e.g. when users set retry for a long period without capacity.
_PENDING_RETRY_DELAYS = [
    timedelta(seconds=15),
    timedelta(seconds=30),
    timedelta(minutes=1),
    timedelta(minutes=2),
    timedelta(minutes=5),
    timedelta(minutes=10),
]


def _get_retry_delay(resubmission_attempt: int) -> timedelta:
    if resubmission_attempt - 1 < len(_PENDING_RETRY_DELAYS):
        return _PENDING_RETRY_DELAYS[resubmission_attempt - 1]
    return _PENDING_RETRY_DELAYS[-1]
