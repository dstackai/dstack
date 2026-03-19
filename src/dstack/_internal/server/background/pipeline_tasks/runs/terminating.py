"""Terminating-run processing helpers for the run pipeline."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import httpx

from dstack._internal.core.errors import GatewayError, SSHError
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server import models
from dstack._internal.server.background.pipeline_tasks.base import ItemUpdateMap
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services import events
from dstack._internal.server.services.gateways import get_or_add_gateway_connection
from dstack._internal.server.services.jobs import stop_runner
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import _get_next_triggered_at, get_run_spec
from dstack._internal.utils.common import get_current_datetime, get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class RunUpdateMap(ItemUpdateMap, total=False):
    status: RunStatus
    next_triggered_at: Optional[datetime]
    fleet_id: Optional[uuid.UUID]


class JobUpdateMap(ItemUpdateMap, total=False):
    status: JobStatus
    termination_reason: Optional[JobTerminationReason]
    remove_at: Optional[datetime]


@dataclass
class ServiceUnregistration:
    event_message: str
    gateway_target: Optional[events.Target]


@dataclass
class TerminatingContext:
    run_model: models.RunModel
    locked_job_models: list[models.JobModel]


@dataclass
class TerminatingResult:
    run_update_map: RunUpdateMap = field(default_factory=RunUpdateMap)
    job_id_to_update_map: dict[uuid.UUID, JobUpdateMap] = field(default_factory=dict)
    service_unregistration: Optional[ServiceUnregistration] = None


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
    if len(context.locked_job_models) > 0:
        delayed_job_ids = []
        regular_job_ids = []
        for job_model in context.locked_job_models:
            if job_model.status == JobStatus.RUNNING and job_termination_reason not in {
                JobTerminationReason.ABORTED_BY_USER,
                JobTerminationReason.DONE_BY_RUNNER,
            }:
                # Send a signal to stop the job gracefully.
                await stop_runner(
                    job_model=job_model, instance_model=get_or_error(job_model.instance)
                )
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

    service_unregistration = None
    if run_model.service_spec is not None:
        try:
            service_unregistration = await _unregister_service(run_model)
        except Exception as e:
            logger.warning("%s: failed to unregister service: %s", fmt(run_model), repr(e))

    return TerminatingResult(
        run_update_map=_get_run_update_map(run_model),
        service_unregistration=service_unregistration,
    )


def _get_job_id_to_update_map(
    delayed_job_ids: list[uuid.UUID],
    regular_job_ids: list[uuid.UUID],
    job_termination_reason: JobTerminationReason,
) -> dict[uuid.UUID, JobUpdateMap]:
    job_id_to_update_map = {}
    for job_id in regular_job_ids:
        job_id_to_update_map[job_id] = JobUpdateMap(
            status=JobStatus.TERMINATING,
            termination_reason=job_termination_reason,
        )
    for job_id in delayed_job_ids:
        job_id_to_update_map[job_id] = JobUpdateMap(
            status=JobStatus.TERMINATING,
            termination_reason=job_termination_reason,
            remove_at=get_current_datetime() + timedelta(seconds=15),
        )
    return job_id_to_update_map


def _get_run_update_map(run_model: models.RunModel) -> RunUpdateMap:
    termination_reason = get_or_error(run_model.termination_reason)
    run_spec = get_run_spec(run_model)
    if run_spec.merged_profile.schedule is not None and termination_reason not in {
        RunTerminationReason.ABORTED_BY_USER,
        RunTerminationReason.STOPPED_BY_USER,
    }:
        return RunUpdateMap(
            status=RunStatus.PENDING,
            next_triggered_at=_get_next_triggered_at(run_spec),
            fleet_id=None,
        )
    return RunUpdateMap(status=termination_reason.to_status())


async def _unregister_service(run_model: models.RunModel) -> Optional[ServiceUnregistration]:
    if run_model.gateway_id is None:  # in-server proxy
        return None

    async with get_session_ctx() as session:
        gateway, conn = await get_or_add_gateway_connection(session, run_model.gateway_id)
        gateway_target = events.Target.from_model(gateway)

    try:
        logger.debug("%s: unregistering service", fmt(run_model))
        async with conn.client() as client:
            await client.unregister_service(
                project=run_model.project.name,
                run_name=run_model.run_name,
            )
        event_message = "Service unregistered from gateway"
    except GatewayError as e:
        # Ignore if the service is not registered.
        logger.warning("%s: unregistering service: %s", fmt(run_model), e)
        event_message = f"Gateway error when unregistering service: {e}"
    except (httpx.RequestError, SSHError) as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))
    return ServiceUnregistration(
        event_message=event_message,
        gateway_target=gateway_target,
    )
