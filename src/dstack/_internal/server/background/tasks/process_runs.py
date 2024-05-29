import asyncio
import datetime
import itertools
import uuid
from typing import List, Optional, Set, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.server.services.gateways as gateways
import dstack._internal.server.services.gateways.autoscalers as autoscalers
from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.profiles import RetryEvent
from dstack._internal.core.models.runs import (
    Job,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    find_job,
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
)
from dstack._internal.server.services.runs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    create_job_model_for_new_submission,
    fmt,
    process_terminating_run,
    retry_run_replica_jobs,
    run_model_to_run,
    scale_run_replicas,
)
from dstack._internal.server.utils.common import wait_unlock
from dstack._internal.utils import common
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
PROCESSING_INTERVAL = datetime.timedelta(seconds=2)
RETRY_DELAY = datetime.timedelta(seconds=15)


async def process_runs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK:
            res = await session.execute(
                sa.select(RunModel).where(
                    RunModel.status.not_in(RunStatus.finished_statuses()),
                    RunModel.last_processed_at
                    < common.get_current_datetime() - PROCESSING_INTERVAL,
                    RunModel.id.not_in(PROCESSING_RUNS_IDS),
                )
            )
            runs = res.scalars().all()
            unprocessed_runs_ids = set(run.id for run in runs)
            PROCESSING_RUNS_IDS.update(unprocessed_runs_ids)

    futures = [process_single_run(run.id, [job.id for job in run.jobs]) for run in runs]
    try:
        for future in asyncio.as_completed(futures):
            run_id = await future
            # Unlock job processing as soon as possible.
            PROCESSING_RUNS_IDS.remove(run_id)
            unprocessed_runs_ids.remove(run_id)
    finally:
        # Ensure that all runs are unlocked.
        # Note that runs should not be unlocked twice!
        PROCESSING_RUNS_IDS.difference_update(unprocessed_runs_ids)


async def process_single_run(run_id: uuid.UUID, job_ids: List[uuid.UUID]) -> uuid.UUID:
    jobs_ids_set = set(job_ids)
    await wait_unlock(SUBMITTED_PROCESSING_JOBS_LOCK, SUBMITTED_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(RUNNING_PROCESSING_JOBS_LOCK, RUNNING_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(
        TERMINATING_PROCESSING_JOBS_LOCK, TERMINATING_PROCESSING_JOBS_IDS, jobs_ids_set
    )

    async with get_session_ctx() as session:
        res = await session.execute(
            sa.select(RunModel)
            .where(RunModel.id == run_id)
            .execution_options(populate_existing=True)
            .options(joinedload(RunModel.project))
            .options(joinedload(RunModel.user))
            .options(joinedload(RunModel.repo))
        )
        run = res.scalar()
        if run is None:
            logger.error(f"Run {run_id} not found")
            return run_id

        try:
            if run.status == RunStatus.PENDING:
                await process_pending_run(session, run)
            elif run.status in {RunStatus.SUBMITTED, RunStatus.PROVISIONING, RunStatus.RUNNING}:
                await process_active_run(session, run)
            elif run.status == RunStatus.TERMINATING:
                await process_terminating_run(session, run)
            else:
                logger.error("%s: unexpected status %s", fmt(run), run.status.name)
                run.status = RunStatus.TERMINATING
                run.termination_reason = RunTerminationReason.SERVER_ERROR
        except ServerError as e:
            logger.error("%s: run processing error: %s", fmt(run), e)
            run.status = RunStatus.TERMINATING
            run.termination_reason = RunTerminationReason.SERVER_ERROR

        run.last_processed_at = common.get_current_datetime()
        await session.commit()

    return run_id


async def process_pending_run(session: AsyncSession, run_model: RunModel):
    """Jobs are not created yet"""
    run = run_model_to_run(run_model)
    if run.latest_job_submission is None:
        logger.error("%s: failed to retry: pending run has no job submissions.")
        run_model.status = RunStatus.FAILED
        run_model.termination_reason = RunTerminationReason.SERVER_ERROR
        return

    if common.get_current_datetime() - run.latest_job_submission.last_processed_at < RETRY_DELAY:
        logger.debug("%s: pending run is not yet ready for resubmission", fmt(run_model))
        return

    # TODO(egor-s) consolidate with `scale_run_replicas` if possible
    replicas = 1
    if run.run_spec.configuration.type == "service":
        replicas = run.run_spec.configuration.replicas.min or 0  # new default
        scaler = autoscalers.get_service_autoscaler(run.run_spec.configuration)
        if scaler is not None:
            conn = await gateways.get_gateway_connection(session, run_model.gateway_id)
            stats = await conn.get_stats(run_model.id)
            if stats:
                # replicas info doesn't matter for now
                replicas = scaler.scale([], stats)
    if replicas == 0:
        # stay zero scaled
        return

    scheduled_replicas = 0
    # Resubmit existing replicas
    for replica_num, replica_jobs in itertools.groupby(
        run.jobs, key=lambda j: j.job_spec.replica_num
    ):
        if scheduled_replicas >= replicas:
            break
        scheduled_replicas += 1
        for job in replica_jobs:
            new_job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=job,
                status=JobStatus.SUBMITTED,
            )
            session.add(new_job_model)
    # Create missing replicas
    for replica_num in range(scheduled_replicas, replicas):
        jobs = await get_jobs_from_run_spec(run.run_spec, replica_num=replica_num)
        for job in jobs:
            job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=job,
                status=JobStatus.SUBMITTED,
            )
            session.add(job_model)

    run_model.status = RunStatus.SUBMITTED
    logger.info("%s: run status has changed PENDING -> SUBMITTED", fmt(run_model))


async def process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, provisioning, or running.
    We handle fails, scaling, and status changes.
    """
    run = run_model_to_run(run_model)
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    retry_single_job = can_retry_single_job(run_spec)

    run_statuses: Set[RunStatus] = set()
    run_termination_reasons: Set[RunTerminationReason] = set()
    replicas_to_retry: List[Tuple[int, List[JobModel]]] = []

    replicas_info: List[autoscalers.ReplicaInfo] = []
    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        replica_statuses: Set[RunStatus] = set()
        replica_needs_retry = False

        replica_active = True
        for job_model in job_models:
            job = find_job(run.jobs, job_model.replica_num, job_model.job_num)
            if job_model.status == JobStatus.DONE or (
                job_model.status == JobStatus.TERMINATING
                and job_model.termination_reason == JobTerminationReason.DONE_BY_RUNNER
            ):
                # the job is done or going to be done
                replica_statuses.add(RunStatus.DONE)
                # for some reason the replica is done, it's not active
                replica_active = False
            elif job_model.termination_reason == JobTerminationReason.SCALED_DOWN:
                # the job was scaled down
                replica_active = False
            elif job_model.status == JobStatus.RUNNING:
                # the job is running
                replica_statuses.add(RunStatus.RUNNING)
            elif job_model.status in {JobStatus.PROVISIONING, JobStatus.PULLING}:
                # the job is provisioning
                replica_statuses.add(RunStatus.PROVISIONING)
            elif job_model.status == JobStatus.SUBMITTED:
                # the job is submitted
                replica_statuses.add(RunStatus.SUBMITTED)
            elif job_model.status == JobStatus.FAILED or (
                job_model.status == JobStatus.TERMINATING
                and job_model.termination_reason
                not in {JobTerminationReason.DONE_BY_RUNNER, JobTerminationReason.SCALED_DOWN}
            ):
                current_duration = should_retry_job(run, job, job_model)
                if current_duration is None:
                    replica_statuses.add(RunStatus.FAILED)
                    run_termination_reasons.add(RunTerminationReason.JOB_FAILED)
                else:
                    if is_retry_duration_exceeded(job, current_duration):
                        replica_statuses.add(RunStatus.FAILED)
                        run_termination_reasons.add(RunTerminationReason.RETRY_LIMIT_EXCEEDED)
                    else:
                        replica_needs_retry = True
            elif job_model.status in {
                JobStatus.TERMINATING,
                JobStatus.TERMINATED,
                JobStatus.ABORTED,
            }:
                pass  # unexpected, but let's ignore it
            else:
                raise ValueError(f"Unexpected job status {job_model.status}")

        if RunStatus.FAILED in replica_statuses:
            run_statuses.add(RunStatus.FAILED)
        else:
            if replica_needs_retry:
                replicas_to_retry.append((replica_num, job_models))
            if not replica_needs_retry or retry_single_job:
                run_statuses.update(replica_statuses)

        if replica_active:
            # submitted_at = replica created
            replicas_info.append(
                autoscalers.ReplicaInfo(
                    active=True,
                    timestamp=min(job.submitted_at for job in job_models).replace(
                        tzinfo=datetime.timezone.utc
                    ),
                )
            )
        else:
            # last_processed_at = replica scaled down
            replicas_info.append(
                autoscalers.ReplicaInfo(
                    active=False,
                    timestamp=max(job.last_processed_at for job in job_models).replace(
                        tzinfo=datetime.timezone.utc
                    ),
                )
            )

    termination_reason: Optional[RunTerminationReason] = None
    if RunStatus.FAILED in run_statuses:
        new_status = RunStatus.TERMINATING
        if RunTerminationReason.JOB_FAILED in run_termination_reasons:
            termination_reason = RunTerminationReason.JOB_FAILED
        elif RunTerminationReason.RETRY_LIMIT_EXCEEDED in run_termination_reasons:
            termination_reason = RunTerminationReason.RETRY_LIMIT_EXCEEDED
        else:
            raise ValueError(f"Unexpected termination reason {run_termination_reasons}")
    elif RunStatus.RUNNING in run_statuses:
        new_status = RunStatus.RUNNING
    elif RunStatus.PROVISIONING in run_statuses:
        new_status = RunStatus.PROVISIONING
    elif RunStatus.SUBMITTED in run_statuses:
        new_status = RunStatus.SUBMITTED
    elif RunStatus.DONE in run_statuses and not replicas_to_retry:
        new_status = RunStatus.TERMINATING
        termination_reason = RunTerminationReason.ALL_JOBS_DONE
    else:
        new_status = RunStatus.PENDING

    # Terminate active jobs if the run is to be resubmitted
    if new_status == RunStatus.PENDING and not retry_single_job:
        for _, replica_jobs in replicas_to_retry:
            for job_model in replica_jobs:
                if not (
                    job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING
                ):
                    job_model.status = JobStatus.TERMINATING
                    job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER

    if new_status not in {RunStatus.TERMINATING, RunStatus.PENDING}:
        # No need to retry if the run is terminating,
        # pending run will retry replicas in `process_pending_run`
        for _, replica_jobs in replicas_to_retry:
            await retry_run_replica_jobs(
                session, run_model, replica_jobs, only_failed=retry_single_job
            )

        if run_spec.configuration.type == "service":
            scaler = autoscalers.get_service_autoscaler(run_spec.configuration)
            if scaler is not None:
                conn = await gateways.get_gateway_connection(session, run_model.gateway_id)
                stats = await conn.get_stats(run_model.id)
                if stats:
                    # use replicas_info from before retrying
                    replicas_diff = scaler.scale(replicas_info, stats)
                    if replicas_diff != 0:
                        await session.flush()
                        await session.refresh(run_model)
                        await scale_run_replicas(session, run_model, replicas_diff)

    if run_model.status != new_status:
        logger.info(
            "%s: run status has changed %s -> %s",
            fmt(run_model),
            run_model.status.name,
            new_status.name,
        )
        run_model.status = new_status
        run_model.termination_reason = termination_reason


def should_retry_job(run: Run, job: Job, job_model: JobModel) -> Optional[datetime.timedelta]:
    """
    Checks if the job should be retried.
    Returns the current duration of retrying if retry is enabled.
    """
    if job.job_spec.retry is None:
        return None

    last_provisioned_submission = None
    for job_submission in reversed(job.job_submissions):
        if job_submission.job_provisioning_data is not None:
            last_provisioned_submission = job_submission
            break

    if (
        job_model.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        and last_provisioned_submission is None
        and RetryEvent.NO_CAPACITY in job.job_spec.retry.on_events
    ):
        return common.get_current_datetime() - run.submitted_at

    if last_provisioned_submission is None:
        return None

    if (
        last_provisioned_submission.termination_reason
        == JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
        and RetryEvent.INTERRUPTION in job.job_spec.retry.on_events
    ):
        return common.get_current_datetime() - last_provisioned_submission.last_processed_at

    if (
        last_provisioned_submission.termination_reason
        in [
            JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
            JobTerminationReason.CREATING_CONTAINER_ERROR,
            JobTerminationReason.EXECUTOR_ERROR,
            JobTerminationReason.GATEWAY_ERROR,
            JobTerminationReason.WAITING_INSTANCE_LIMIT_EXCEEDED,
            JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED,
            JobTerminationReason.PORTS_BINDING_FAILED,
        ]
        and RetryEvent.ERROR in job.job_spec.retry.on_events
    ):
        return common.get_current_datetime() - last_provisioned_submission.last_processed_at

    return None


def is_retry_duration_exceeded(job: Job, current_duration: datetime.timedelta) -> bool:
    if job.job_spec.retry is None:
        return True
    return current_duration > datetime.timedelta(seconds=job.job_spec.retry.duration)


def can_retry_single_job(run_spec: RunSpec) -> bool:
    # TODO: Currently, we terminate and retry the entire replica if one of the job fails.
    # We could make partial retry in some multi-node cases.
    # E.g. restarting a worker node, independent jobs.
    return False
