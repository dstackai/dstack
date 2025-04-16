import asyncio
import datetime
import itertools
from typing import List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

import dstack._internal.server.services.gateways as gateways
import dstack._internal.server.services.services.autoscalers as autoscalers
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
from dstack._internal.server.models import JobModel, ProjectModel, RunModel
from dstack._internal.server.services.jobs import (
    find_job,
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.runs import (
    create_job_model_for_new_submission,
    fmt,
    process_terminating_run,
    retry_run_replica_jobs,
    run_model_to_run,
    scale_run_replicas,
)
from dstack._internal.utils import common
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_runs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_run())
    await asyncio.gather(*tasks)


async def _process_next_run():
    run_lock, run_lockset = get_locker().get_lockset(RunModel.__tablename__)
    job_lock, job_lockset = get_locker().get_lockset(JobModel.__tablename__)
    async with get_session_ctx() as session:
        async with run_lock, job_lock:
            res = await session.execute(
                select(RunModel)
                .where(
                    RunModel.status.not_in(RunStatus.finished_statuses()),
                    RunModel.id.not_in(run_lockset),
                )
                .order_by(RunModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            run_model = res.scalar()
            if run_model is None:
                return
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.run_id == run_model.id,
                    JobModel.id.not_in(job_lockset),
                )
                .order_by(JobModel.id)  # take locks in order
                .with_for_update(skip_locked=True)
            )
            job_models = res.scalars().all()
            if len(run_model.jobs) != len(job_models):
                # Some jobs are locked
                return
            job_ids = [j.id for j in run_model.jobs]
            run_lockset.add(run_model.id)
            job_lockset.update(job_ids)
        try:
            run_model_id = run_model.id
            await _process_run(session=session, run_model=run_model)
        finally:
            run_lockset.difference_update([run_model_id])
            job_lockset.difference_update(job_ids)


async def _process_run(session: AsyncSession, run_model: RunModel):
    logger.debug("%s: processing run", fmt(run_model))
    # Refetch to load related attributes.
    # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == run_model.id)
        .execution_options(populate_existing=True)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
        .options(selectinload(RunModel.jobs).joinedload(JobModel.instance))
        .execution_options(populate_existing=True)
    )
    run_model = res.unique().scalar_one()
    try:
        if run_model.status == RunStatus.PENDING:
            await _process_pending_run(session, run_model)
        elif run_model.status in {RunStatus.SUBMITTED, RunStatus.PROVISIONING, RunStatus.RUNNING}:
            await _process_active_run(session, run_model)
        elif run_model.status == RunStatus.TERMINATING:
            await process_terminating_run(session, run_model)
        else:
            logger.error("%s: unexpected status %s", fmt(run_model), run_model.status.name)
            run_model.status = RunStatus.TERMINATING
            run_model.termination_reason = RunTerminationReason.SERVER_ERROR
    except ServerError as e:
        logger.error("%s: run processing error: %s", fmt(run_model), e)
        run_model.status = RunStatus.TERMINATING
        run_model.termination_reason = RunTerminationReason.SERVER_ERROR

    run_model.last_processed_at = common.get_current_datetime()
    await session.commit()


async def _process_pending_run(session: AsyncSession, run_model: RunModel):
    """Jobs are not created yet"""
    run = run_model_to_run(run_model)
    if not _pending_run_ready_for_resubmission(run_model, run):
        logger.debug("%s: pending run is not yet ready for resubmission", fmt(run_model))
        return

    # TODO(egor-s) consolidate with `scale_run_replicas` if possible
    replicas = 1
    if run.run_spec.configuration.type == "service":
        replicas = run.run_spec.configuration.replicas.min or 0  # new default
        scaler = autoscalers.get_service_scaler(run.run_spec.configuration)
        stats = None
        if run_model.gateway_id is not None:
            conn = await gateways.get_or_add_gateway_connection(session, run_model.gateway_id)
            stats = await conn.get_stats(run_model.project.name, run_model.run_name)
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


def _pending_run_ready_for_resubmission(run_model: RunModel, run: Run) -> bool:
    if run.latest_job_submission is None:
        # Should not be possible
        return True
    duration_since_processing = (
        common.get_current_datetime() - run.latest_job_submission.last_processed_at
    )
    if duration_since_processing < _get_retry_delay(run_model.resubmission_attempt):
        return False
    return True


# We use exponentially increasing retry delays for pending runs.
# This prevents creation of too many job submissions for runs stuck in pending,
# e.g. when users set retry for a long period without capacity.
_PENDING_RETRY_DELAYS = [
    datetime.timedelta(seconds=15),
    datetime.timedelta(seconds=30),
    datetime.timedelta(minutes=1),
    datetime.timedelta(minutes=2),
    datetime.timedelta(minutes=5),
    datetime.timedelta(minutes=10),
]


def _get_retry_delay(resubmission_attempt: int) -> datetime.timedelta:
    if resubmission_attempt - 1 < len(_PENDING_RETRY_DELAYS):
        return _PENDING_RETRY_DELAYS[resubmission_attempt - 1]
    return _PENDING_RETRY_DELAYS[-1]


async def _process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, provisioning, or running.
    We handle fails, scaling, and status changes.
    """
    run = run_model_to_run(run_model)
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    retry_single_job = _can_retry_single_job(run_spec)

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
            if (
                run_model.fleet_id is None
                and job_model.instance is not None
                and job_model.instance.fleet_id is not None
            ):
                run_model.fleet_id = job_model.instance.fleet_id
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
                job_model.status
                in [JobStatus.TERMINATING, JobStatus.TERMINATED, JobStatus.ABORTED]
                and job_model.termination_reason
                not in {JobTerminationReason.DONE_BY_RUNNER, JobTerminationReason.SCALED_DOWN}
            ):
                current_duration = _should_retry_job(run, job, job_model)
                if current_duration is None:
                    replica_statuses.add(RunStatus.FAILED)
                    run_termination_reasons.add(RunTerminationReason.JOB_FAILED)
                else:
                    if _is_retry_duration_exceeded(job, current_duration):
                        replica_statuses.add(RunStatus.FAILED)
                        run_termination_reasons.add(RunTerminationReason.RETRY_LIMIT_EXCEEDED)
                    else:
                        replica_needs_retry = True
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
            scaler = autoscalers.get_service_scaler(run_spec.configuration)
            stats = None
            if run_model.gateway_id is not None:
                conn = await gateways.get_or_add_gateway_connection(session, run_model.gateway_id)
                stats = await conn.get_stats(run_model.project.name, run_model.run_name)
            # use replicas_info from before retrying
            replicas_diff = scaler.scale(replicas_info, stats)
            if replicas_diff != 0:
                # FIXME: potentially long write transaction
                # Why do we flush here?
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
        # While a run goes to pending without provisioning, resubmission_attempt increases.
        if new_status == RunStatus.PROVISIONING:
            run_model.resubmission_attempt = 0
        elif new_status == RunStatus.PENDING:
            run_model.resubmission_attempt += 1


def _should_retry_job(run: Run, job: Job, job_model: JobModel) -> Optional[datetime.timedelta]:
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


def _is_retry_duration_exceeded(job: Job, current_duration: datetime.timedelta) -> bool:
    if job.job_spec.retry is None:
        return True
    return current_duration > datetime.timedelta(seconds=job.job_spec.retry.duration)


def _can_retry_single_job(run_spec: RunSpec) -> bool:
    # TODO: Currently, we terminate and retry the entire replica if one of the job fails.
    # We could make partial retry in some multi-node cases.
    # E.g. restarting a worker node, independent jobs.
    return False
