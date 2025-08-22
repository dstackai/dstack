import asyncio
import datetime
from typing import List, Optional, Set, Tuple

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only, selectinload

import dstack._internal.server.services.services.autoscalers as autoscalers
from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.profiles import RetryEvent, StopCriteria
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services.jobs import (
    find_job,
    get_job_specs_from_run_spec,
    group_jobs_by_replica_latest,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.prometheus.client_metrics import run_metrics
from dstack._internal.server.services.runs import (
    fmt,
    is_replica_registered,
    process_terminating_run,
    retry_run_replica_jobs,
    run_model_to_run,
    scale_run_replicas,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.server.services.services import update_service_desired_replica_count
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MIN_PROCESSING_INTERVAL = datetime.timedelta(seconds=5)
ROLLING_DEPLOYMENT_MAX_SURGE = 1  # at most one extra replica during rolling deployment


async def process_runs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_run())
    await asyncio.gather(*tasks)


@sentry_utils.instrument_background_task
async def _process_next_run():
    run_lock, run_lockset = get_locker(get_db().dialect_name).get_lockset(RunModel.__tablename__)
    job_lock, job_lockset = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
    now = common.get_current_datetime()
    async with get_session_ctx() as session:
        async with run_lock, job_lock:
            res = await session.execute(
                select(RunModel)
                .where(
                    RunModel.id.not_in(run_lockset),
                    RunModel.last_processed_at < now - MIN_PROCESSING_INTERVAL,
                    # Filter out runs that don't need to be processed.
                    # This is only to reduce unnecessary commits.
                    # Otherwise, we could fetch all active runs and filter them when processing.
                    or_(
                        # Active non-pending runs:
                        RunModel.status.not_in(
                            RunStatus.finished_statuses() + [RunStatus.PENDING]
                        ),
                        # Retrying runs:
                        and_(
                            RunModel.status == RunStatus.PENDING,
                            RunModel.resubmission_attempt > 0,
                        ),
                        # Scheduled ready runs:
                        and_(
                            RunModel.status == RunStatus.PENDING,
                            RunModel.resubmission_attempt == 0,
                            RunModel.next_triggered_at.is_not(None),
                            RunModel.next_triggered_at < now,
                        ),
                        # Scaled-to-zero runs:
                        # Such runs cannot be scheduled, thus we check next_triggered_at.
                        # If we allow scheduled services with downscaling to zero
                        # This check won't pass.
                        and_(
                            RunModel.status == RunStatus.PENDING,
                            RunModel.resubmission_attempt == 0,
                            RunModel.next_triggered_at.is_(None),
                        ),
                    ),
                )
                .options(joinedload(RunModel.jobs).load_only(JobModel.id))
                .options(load_only(RunModel.id))
                .order_by(RunModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True, key_share=True, of=RunModel)
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
                .with_for_update(skip_locked=True, key_share=True)
            )
            job_models = res.scalars().all()
            if len(run_model.jobs) != len(job_models):
                # Some jobs are locked
                return
            job_ids = [j.id for j in run_model.jobs]
            run_lockset.add(run_model.id)
            job_lockset.update(job_ids)
        run_model_id = run_model.id
        try:
            await _process_run(session=session, run_model=run_model)
        finally:
            run_lockset.difference_update([run_model_id])
            job_lockset.difference_update(job_ids)


async def _process_run(session: AsyncSession, run_model: RunModel):
    # Refetch to load related attributes.
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == run_model.id)
        .execution_options(populate_existing=True)
        .options(joinedload(RunModel.project).load_only(ProjectModel.id, ProjectModel.name))
        .options(joinedload(RunModel.user).load_only(UserModel.name))
        .options(
            selectinload(RunModel.jobs)
            .joinedload(JobModel.instance)
            .load_only(InstanceModel.fleet_id)
        )
        .execution_options(populate_existing=True)
    )
    run_model = res.unique().scalar_one()
    logger.debug("%s: processing run", fmt(run_model))
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

    # TODO: Do not select such runs in the first place to avoid redundant processing
    if run_model.resubmission_attempt > 0 and not _retrying_run_ready_for_resubmission(
        run_model, run
    ):
        logger.debug("%s: retrying run is not yet ready for resubmission", fmt(run_model))
        return

    run_model.desired_replica_count = 1
    if run.run_spec.configuration.type == "service":
        run_model.desired_replica_count = run.run_spec.configuration.replicas.min or 0
        await update_service_desired_replica_count(
            session,
            run_model,
            run.run_spec.configuration,
            # does not matter for pending services, since 0->n scaling should happen without delay
            last_scaled_at=None,
        )

    if run_model.desired_replica_count == 0:
        # stay zero scaled
        return

    await scale_run_replicas(session, run_model, replicas_diff=run_model.desired_replica_count)

    run_model.status = RunStatus.SUBMITTED
    logger.info("%s: run status has changed PENDING -> SUBMITTED", fmt(run_model))


def _retrying_run_ready_for_resubmission(run_model: RunModel, run: Run) -> bool:
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
    run_spec = run.run_spec
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
    elif _should_stop_on_master_done(run):
        new_status = RunStatus.TERMINATING
        # ALL_JOBS_DONE is used for all DONE reasons including master-done
        termination_reason = RunTerminationReason.ALL_JOBS_DONE
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
        # No need to retry, scale, or redeploy replicas if the run is terminating,
        # pending run will retry replicas in `process_pending_run`
        await _handle_run_replicas(
            session, run_model, run_spec, replicas_to_retry, retry_single_job, replicas_info
        )

    if run_model.status != new_status:
        logger.info(
            "%s: run status has changed %s -> %s",
            fmt(run_model),
            run_model.status.name,
            new_status.name,
        )
        if run_model.status == RunStatus.SUBMITTED and new_status == RunStatus.PROVISIONING:
            current_time = common.get_current_datetime()
            submit_to_provision_duration = (current_time - run_model.submitted_at).total_seconds()
            logger.info(
                "%s: run took %.2f seconds from submission to provisioning.",
                fmt(run_model),
                submit_to_provision_duration,
            )
            project_name = run_model.project.name
            run_metrics.log_submit_to_provision_duration(
                submit_to_provision_duration, project_name, run_spec.configuration.type
            )

        if new_status == RunStatus.PENDING:
            run_metrics.increment_pending_runs(run_model.project.name, run_spec.configuration.type)
            # Unassign run from fleet so that the new fleet can be chosen when retrying
            run_model.fleet = None

        run_model.status = new_status
        run_model.termination_reason = termination_reason
        # While a run goes to pending without provisioning, resubmission_attempt increases.
        if new_status == RunStatus.PROVISIONING:
            run_model.resubmission_attempt = 0
        elif new_status == RunStatus.PENDING:
            run_model.resubmission_attempt += 1


async def _handle_run_replicas(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
    replicas_to_retry: list[tuple[int, list[JobModel]]],
    retry_single_job: bool,
    replicas_info: list[autoscalers.ReplicaInfo],
) -> None:
    """
    Does ONE of:
    - replica retry
    - replica scaling
    - replica rolling deployment

    Does not do everything at once to avoid conflicts between the stages and long DB transactions.
    """

    if replicas_to_retry:
        for _, replica_jobs in replicas_to_retry:
            await retry_run_replica_jobs(
                session, run_model, replica_jobs, only_failed=retry_single_job
            )
        return

    if run_spec.configuration.type == "service":
        await update_service_desired_replica_count(
            session,
            run_model,
            run_spec.configuration,
            # FIXME: should only include scaling events, not retries and deployments
            last_scaled_at=max((r.timestamp for r in replicas_info), default=None),
        )

    max_replica_count = run_model.desired_replica_count
    if _has_out_of_date_replicas(run_model):
        # allow extra replicas when deployment is in progress
        max_replica_count += ROLLING_DEPLOYMENT_MAX_SURGE

    active_replica_count = sum(1 for r in replicas_info if r.active)
    if active_replica_count not in range(run_model.desired_replica_count, max_replica_count + 1):
        await scale_run_replicas(
            session,
            run_model,
            replicas_diff=run_model.desired_replica_count - active_replica_count,
        )
        return

    await _update_jobs_to_new_deployment_in_place(
        session=session,
        run_model=run_model,
        run_spec=run_spec,
    )
    if _has_out_of_date_replicas(run_model):
        assert run_spec.configuration.type == "service", (
            "Rolling deployment is only supported for services"
        )
        non_terminated_replica_count = len(
            {j.replica_num for j in run_model.jobs if not j.status.is_finished()}
        )
        # Avoid using too much hardware during a deployment - never have
        # more than max_replica_count non-terminated replicas.
        if non_terminated_replica_count < max_replica_count:
            # Start more up-to-date replicas that will eventually replace out-of-date replicas.
            await scale_run_replicas(
                session,
                run_model,
                replicas_diff=max_replica_count - non_terminated_replica_count,
            )

        replicas_to_stop_count = 0
        # stop any out-of-date replicas that are not registered
        replicas_to_stop_count += sum(
            any(j.deployment_num < run_model.deployment_num for j in jobs)
            and any(
                j.status not in [JobStatus.TERMINATING] + JobStatus.finished_statuses()
                for j in jobs
            )
            and not is_replica_registered(jobs)
            for _, jobs in group_jobs_by_replica_latest(run_model.jobs)
        )
        # stop excessive registered out-of-date replicas, except those that are already `terminating`
        non_terminating_registered_replicas_count = sum(
            is_replica_registered(jobs) and all(j.status != JobStatus.TERMINATING for j in jobs)
            for _, jobs in group_jobs_by_replica_latest(run_model.jobs)
        )
        replicas_to_stop_count += max(
            0, non_terminating_registered_replicas_count - run_model.desired_replica_count
        )
        if replicas_to_stop_count:
            await scale_run_replicas(
                session,
                run_model,
                replicas_diff=-replicas_to_stop_count,
            )


async def _update_jobs_to_new_deployment_in_place(
    session: AsyncSession, run_model: RunModel, run_spec: RunSpec
) -> None:
    """
    Bump deployment_num for jobs that do not require redeployment.
    """
    secrets = await get_project_secrets_mapping(
        session=session,
        project=run_model.project,
    )
    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        if all(j.status.is_finished() for j in job_models):
            continue
        if all(j.deployment_num == run_model.deployment_num for j in job_models):
            continue
        # FIXME: Handle getting image configuration errors or skip it.
        new_job_specs = await get_job_specs_from_run_spec(
            run_spec=run_spec,
            secrets=secrets,
            replica_num=replica_num,
        )
        assert len(new_job_specs) == len(job_models), (
            "Changing the number of jobs within a replica is not yet supported"
        )
        can_update_all_jobs = True
        for old_job_model, new_job_spec in zip(job_models, new_job_specs):
            old_job_spec = JobSpec.__response__.parse_raw(old_job_model.job_spec_data)
            if new_job_spec != old_job_spec:
                can_update_all_jobs = False
                break
        if can_update_all_jobs:
            for job_model in job_models:
                job_model.deployment_num = run_model.deployment_num


def _has_out_of_date_replicas(run: RunModel) -> bool:
    for job in run.jobs:
        if job.deployment_num < run.deployment_num and not (
            job.status.is_finished() or job.termination_reason == JobTerminationReason.SCALED_DOWN
        ):
            return True
    return False


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
        job_model.termination_reason is not None
        and job_model.termination_reason.to_retry_event() == RetryEvent.NO_CAPACITY
        and last_provisioned_submission is None
        and RetryEvent.NO_CAPACITY in job.job_spec.retry.on_events
    ):
        return common.get_current_datetime() - run.submitted_at

    if last_provisioned_submission is None:
        return None

    if (
        last_provisioned_submission.termination_reason is not None
        and JobTerminationReason(last_provisioned_submission.termination_reason).to_retry_event()
        in job.job_spec.retry.on_events
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


def _should_stop_on_master_done(run: Run) -> bool:
    if run.run_spec.merged_profile.stop_criteria != StopCriteria.MASTER_DONE:
        return False
    for job in run.jobs:
        if job.job_spec.job_num == 0 and job.job_submissions[-1].status == JobStatus.DONE:
            return True
    return False
