import asyncio
import datetime
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload, load_only, with_loader_criteria

import dstack._internal.server.services.services.autoscalers as autoscalers
from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.configurations import ReplicaGroup
from dstack._internal.core.models.profiles import RetryEvent, StopCriteria
from dstack._internal.core.models.runs import (
    Job,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.jobs import (
    get_job_spec,
    get_job_specs_from_run_spec,
    group_jobs_by_replica_latest,
    is_master_job,
    job_model_to_job_submission,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.prometheus.client_metrics import run_metrics
from dstack._internal.server.services.runs import (
    fmt,
    process_terminating_run,
    run_model_to_run,
    switch_run_status,
)
from dstack._internal.server.services.runs.replicas import (
    build_replica_lists,
    has_out_of_date_replicas,
    is_replica_registered,
    job_belongs_to_group,
    retry_run_replica_jobs,
    scale_down_replicas,
    scale_run_replicas,
    scale_run_replicas_for_all_groups,
    scale_run_replicas_for_group,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.server.services.services import update_service_desired_replica_count
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MIN_PROCESSING_INTERVAL = datetime.timedelta(seconds=5)

# No need to lock finished or terminating jobs since run processing does not update such jobs.
JOB_STATUSES_EXCLUDED_FOR_LOCKING = JobStatus.finished_statuses() + [JobStatus.TERMINATING]

ROLLING_DEPLOYMENT_MAX_SURGE = 1  # at most one extra replica during rolling deployment


async def process_runs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_run())
    await asyncio.gather(*tasks)


@sentry_utils.instrument_scheduled_task
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
                        # If we allow scheduled services with downscaling to zero, this check won't pass.
                        and_(
                            RunModel.status == RunStatus.PENDING,
                            RunModel.resubmission_attempt == 0,
                            RunModel.next_triggered_at.is_(None),
                        ),
                    ),
                )
                .options(
                    joinedload(RunModel.jobs).load_only(JobModel.id),
                    with_loader_criteria(
                        JobModel,
                        JobModel.status.not_in(JOB_STATUSES_EXCLUDED_FOR_LOCKING),
                        include_aliases=True,
                    ),
                )
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
                    JobModel.status.not_in(JOB_STATUSES_EXCLUDED_FOR_LOCKING),
                    JobModel.lock_expires_at.is_(None),
                )
                .options(load_only(JobModel.id))
                .order_by(JobModel.id)  # take locks in order
                .with_for_update(skip_locked=True, key_share=True)
            )
            job_models = res.scalars().all()
            if len(run_model.jobs) != len(job_models):
                # Some jobs are locked or there was a non-repeatable read
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
    run_model = await _refetch_run_model(session, run_model)
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
            run_model.termination_reason = RunTerminationReason.SERVER_ERROR
            switch_run_status(session, run_model, RunStatus.TERMINATING)
    except ServerError as e:
        logger.error("%s: run processing error: %s", fmt(run_model), e)
        run_model.termination_reason = RunTerminationReason.SERVER_ERROR
        switch_run_status(session, run_model, RunStatus.TERMINATING)

    run_model.last_processed_at = common.get_current_datetime()
    await session.commit()


async def _refetch_run_model(session: AsyncSession, run_model: RunModel) -> RunModel:
    # Select only latest submissions for every job.
    latest_submissions_sq = (
        select(
            JobModel.run_id.label("run_id"),
            JobModel.replica_num.label("replica_num"),
            JobModel.job_num.label("job_num"),
            func.max(JobModel.submission_num).label("max_submission_num"),
        )
        .where(JobModel.run_id == run_model.id)
        .group_by(JobModel.run_id, JobModel.replica_num, JobModel.job_num)
        .subquery()
    )
    job_alias = aliased(JobModel)
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == run_model.id)
        .outerjoin(latest_submissions_sq, latest_submissions_sq.c.run_id == RunModel.id)
        .outerjoin(
            job_alias,
            onclause=and_(
                job_alias.run_id == latest_submissions_sq.c.run_id,
                job_alias.replica_num == latest_submissions_sq.c.replica_num,
                job_alias.job_num == latest_submissions_sq.c.job_num,
                job_alias.submission_num == latest_submissions_sq.c.max_submission_num,
            ),
        )
        .options(joinedload(RunModel.project).load_only(ProjectModel.id, ProjectModel.name))
        .options(joinedload(RunModel.user).load_only(UserModel.name))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
        .options(
            contains_eager(RunModel.jobs, alias=job_alias)
            .joinedload(JobModel.instance)
            .load_only(InstanceModel.fleet_id)
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one()


async def _process_pending_run(session: AsyncSession, run_model: RunModel):
    """Jobs are not created yet"""
    run = run_model_to_run(run_model)

    # TODO: Do not select such runs in the first place to avoid redundant processing
    if run_model.resubmission_attempt > 0 and not _retrying_run_ready_for_resubmission(
        run_model, run
    ):
        logger.debug("%s: retrying run is not yet ready for resubmission", fmt(run_model))
        return

    if run.run_spec.configuration.type == "service":
        run_model.desired_replica_count = sum(
            group.count.min or 0 for group in run.run_spec.configuration.replica_groups
        )
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

        replicas: List[ReplicaGroup] = run.run_spec.configuration.replica_groups

        await scale_run_replicas_for_all_groups(session, run_model, replicas)
    else:
        # Non-service pending runs may have 0 job submissions and require new submission, e.g. scheduled tasks.
        run_model.desired_replica_count = 1
        await scale_run_replicas(session, run_model, replicas_diff=run_model.desired_replica_count)

    switch_run_status(session=session, run_model=run_model, new_status=RunStatus.SUBMITTED)


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


@dataclass
class _ReplicaAnalysis:
    """Per-replica classification of job states for determining the run's next status."""

    replica_num: int
    job_models: List[JobModel]
    replica_info: autoscalers.ReplicaInfo
    contributed_statuses: Set[RunStatus] = field(default_factory=set)
    """`RunStatus` values derived from this replica's jobs. Merged into the run-level
    analysis unless the replica is being retried as a whole."""
    termination_reasons: Set[RunTerminationReason] = field(default_factory=set)
    """Why the replica failed. Only populated when `FAILED` is in `contributed_statuses`."""
    needs_retry: bool = False
    """At least one job failed with a retryable reason and the retry duration hasn't been
    exceeded. When `True`, the replica does not contribute its statuses to the run-level
    analysis (unless `retry_single_job` is enabled) and is added to `replicas_to_retry` instead."""


@dataclass
class _RunAnalysis:
    """Aggregated replica analysis used to determine the run's next status.

    Each replica contributes `RunStatus` based on its jobs' statuses.
    The run's new status is the highest-priority value across all
    contributing replicas: FAILED > RUNNING > PROVISIONING > SUBMITTED > DONE.
    Replicas that need full retry do not contribute and instead cause a PENDING transition.
    """

    contributed_statuses: Set[RunStatus] = field(default_factory=set)
    termination_reasons: Set[RunTerminationReason] = field(default_factory=set)
    replicas_to_retry: List[Tuple[int, List[JobModel]]] = field(default_factory=list)
    """Replicas with retryable failures that haven't exceeded the retry duration."""
    replicas_info: List[autoscalers.ReplicaInfo] = field(default_factory=list)
    """Per-replica active/inactive info for the autoscaler."""


@dataclass
class _ActiveRunTransition:
    new_status: RunStatus
    termination_reason: Optional[RunTerminationReason] = None


async def _process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, provisioning, or running.
    We handle fails, scaling, and status changes.
    """
    run = run_model_to_run(run_model)
    run_spec = run.run_spec
    retry_single_job = _can_retry_single_job(run_spec)
    _maybe_set_run_fleet_id_from_jobs(run_model)
    run_jobs_by_position = _get_run_jobs_by_position(run)
    analysis = await _analyze_active_run(
        session=session,
        run_model=run_model,
        run=run,
        run_jobs_by_position=run_jobs_by_position,
        retry_single_job=retry_single_job,
    )
    transition = _get_active_run_transition(run, analysis)
    await _apply_active_run_transition(
        session=session,
        run_model=run_model,
        run_spec=run_spec,
        transition=transition,
        replicas_to_retry=analysis.replicas_to_retry,
        retry_single_job=retry_single_job,
        replicas_info=analysis.replicas_info,
    )


def _get_run_jobs_by_position(run: Run) -> Dict[Tuple[int, int], Job]:
    return {(job.job_spec.replica_num, job.job_spec.job_num): job for job in run.jobs}


async def _analyze_active_run(
    session: AsyncSession,
    run_model: RunModel,
    run: Run,
    run_jobs_by_position: Dict[Tuple[int, int], Job],
    retry_single_job: bool,
) -> _RunAnalysis:
    run_analysis = _RunAnalysis()
    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        replica_analysis = await _analyze_active_run_replica(
            session=session,
            run_model=run_model,
            run=run,
            run_jobs_by_position=run_jobs_by_position,
            replica_num=replica_num,
            job_models=job_models,
        )
        _apply_replica_analysis(run_analysis, replica_analysis, retry_single_job)
    return run_analysis


async def _analyze_active_run_replica(
    session: AsyncSession,
    run_model: RunModel,
    run: Run,
    run_jobs_by_position: Dict[Tuple[int, int], Job],
    replica_num: int,
    job_models: List[JobModel],
) -> _ReplicaAnalysis:
    contributed_statuses: Set[RunStatus] = set()
    termination_reasons: Set[RunTerminationReason] = set()
    needs_retry = False
    replica_active = True
    jobs_done_num = 0

    for job_model in job_models:
        job = run_jobs_by_position[(job_model.replica_num, job_model.job_num)]

        if _job_is_done_or_finishing_done(job_model):
            contributed_statuses.add(RunStatus.DONE)
            jobs_done_num += 1
            continue

        if _job_was_scaled_down(job_model):
            replica_active = False
            continue

        replica_status = _get_non_terminal_replica_status(job_model)
        if replica_status is not None:
            contributed_statuses.add(replica_status)
            continue

        if _job_needs_retry_evaluation(job_model):
            current_duration = await _should_retry_job(session, run, job, job_model)
            if current_duration is None:
                contributed_statuses.add(RunStatus.FAILED)
                termination_reasons.add(RunTerminationReason.JOB_FAILED)
            elif _is_retry_duration_exceeded(job, current_duration):
                contributed_statuses.add(RunStatus.FAILED)
                termination_reasons.add(RunTerminationReason.RETRY_LIMIT_EXCEEDED)
            else:
                needs_retry = True
            continue

        raise ServerError(f"Unexpected job status {job_model.status}")

    if jobs_done_num == len(job_models):
        # Consider replica inactive if all its jobs are done for some reason.
        # If only some jobs are done, replica is considered active to avoid
        # provisioning new replicas for partially done multi-node tasks.
        replica_active = False

    return _ReplicaAnalysis(
        replica_num=replica_num,
        job_models=job_models,
        replica_info=_get_replica_info(job_models, replica_active),
        contributed_statuses=contributed_statuses,
        termination_reasons=termination_reasons,
        needs_retry=needs_retry,
    )


def _apply_replica_analysis(
    analysis: _RunAnalysis,
    replica_analysis: _ReplicaAnalysis,
    retry_single_job: bool,
) -> None:
    analysis.replicas_info.append(replica_analysis.replica_info)

    if RunStatus.FAILED in replica_analysis.contributed_statuses:
        analysis.contributed_statuses.add(RunStatus.FAILED)
        analysis.termination_reasons.update(replica_analysis.termination_reasons)
        return

    if replica_analysis.needs_retry:
        analysis.replicas_to_retry.append(
            (replica_analysis.replica_num, replica_analysis.job_models)
        )

    if not replica_analysis.needs_retry or retry_single_job:
        analysis.contributed_statuses.update(replica_analysis.contributed_statuses)


def _maybe_set_run_fleet_id_from_jobs(run_model: RunModel) -> None:
    """
    The master job gets fleet assigned with the instance.
    The run then gets from the master job's instance, and non-master jobs wait for the run's fleet to be assigned.
    """
    if run_model.fleet_id is not None:
        return

    for job_model in run_model.jobs:
        if job_model.instance is not None and job_model.instance.fleet_id is not None:
            run_model.fleet_id = job_model.instance.fleet_id
            return


def _job_is_done_or_finishing_done(job_model: JobModel) -> bool:
    return job_model.status == JobStatus.DONE or (
        job_model.status == JobStatus.TERMINATING
        and job_model.termination_reason == JobTerminationReason.DONE_BY_RUNNER
    )


def _job_was_scaled_down(job_model: JobModel) -> bool:
    return job_model.termination_reason == JobTerminationReason.SCALED_DOWN


def _get_non_terminal_replica_status(job_model: JobModel) -> Optional[RunStatus]:
    if job_model.status == JobStatus.RUNNING:
        return RunStatus.RUNNING
    if job_model.status in {JobStatus.PROVISIONING, JobStatus.PULLING}:
        return RunStatus.PROVISIONING
    if job_model.status == JobStatus.SUBMITTED:
        return RunStatus.SUBMITTED
    return None


def _job_needs_retry_evaluation(job_model: JobModel) -> bool:
    return job_model.status == JobStatus.FAILED or (
        job_model.status in [JobStatus.TERMINATING, JobStatus.TERMINATED, JobStatus.ABORTED]
        and job_model.termination_reason
        not in {JobTerminationReason.DONE_BY_RUNNER, JobTerminationReason.SCALED_DOWN}
    )


def _get_active_run_transition(run: Run, analysis: _RunAnalysis) -> _ActiveRunTransition:
    # Check `analysis.contributed_statuses` in the priority order.
    if RunStatus.FAILED in analysis.contributed_statuses:
        if RunTerminationReason.JOB_FAILED in analysis.termination_reasons:
            termination_reason = RunTerminationReason.JOB_FAILED
        elif RunTerminationReason.RETRY_LIMIT_EXCEEDED in analysis.termination_reasons:
            termination_reason = RunTerminationReason.RETRY_LIMIT_EXCEEDED
        else:
            raise ServerError(f"Unexpected termination reason {analysis.termination_reasons}")
        return _ActiveRunTransition(
            new_status=RunStatus.TERMINATING,
            termination_reason=termination_reason,
        )

    if _should_stop_on_master_done(run):
        # ALL_JOBS_DONE is used for all DONE reasons including master-done
        return _ActiveRunTransition(
            new_status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.ALL_JOBS_DONE,
        )

    if RunStatus.RUNNING in analysis.contributed_statuses:
        return _ActiveRunTransition(new_status=RunStatus.RUNNING)
    if RunStatus.PROVISIONING in analysis.contributed_statuses:
        return _ActiveRunTransition(new_status=RunStatus.PROVISIONING)
    if RunStatus.SUBMITTED in analysis.contributed_statuses:
        return _ActiveRunTransition(new_status=RunStatus.SUBMITTED)
    if RunStatus.DONE in analysis.contributed_statuses and not analysis.replicas_to_retry:
        return _ActiveRunTransition(
            new_status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.ALL_JOBS_DONE,
        )
    if not analysis.contributed_statuses or analysis.contributed_statuses == {RunStatus.DONE}:
        # No active replicas remain — resubmit the entire run.
        # `contributed_statuses` is either empty (every replica is retrying) or contains
        # only DONE (some replicas finished, others need retry).
        return _ActiveRunTransition(new_status=RunStatus.PENDING)
    raise ServerError("Failed to determine run transition: unexpected active run state")


async def _apply_active_run_transition(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
    transition: _ActiveRunTransition,
    replicas_to_retry: List[Tuple[int, List[JobModel]]],
    retry_single_job: bool,
    replicas_info: List[autoscalers.ReplicaInfo],
) -> None:
    if transition.new_status == RunStatus.PENDING and not retry_single_job:
        _terminate_retrying_replica_jobs(session, replicas_to_retry)

    if transition.new_status not in {RunStatus.TERMINATING, RunStatus.PENDING}:
        # No need to retry, scale, or redeploy replicas if the run is terminating,
        # pending run will retry replicas in `process_pending_run`
        await _handle_run_replicas(
            session,
            run_model,
            run_spec,
            replicas_to_retry,
            retry_single_job,
            replicas_info,
        )

    _maybe_switch_active_run_status(session, run_model, run_spec, transition)


def _terminate_retrying_replica_jobs(
    session: AsyncSession,
    replicas_to_retry: List[Tuple[int, List[JobModel]]],
) -> None:
    for _, replica_jobs in replicas_to_retry:
        for job_model in replica_jobs:
            if job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING:
                continue
            job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
            job_model.termination_reason_message = "Run is to be resubmitted"
            switch_job_status(session, job_model, JobStatus.TERMINATING)


def _maybe_switch_active_run_status(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
    transition: _ActiveRunTransition,
) -> None:
    if run_model.status == transition.new_status:
        return

    if run_model.status == RunStatus.SUBMITTED and transition.new_status == RunStatus.PROVISIONING:
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

    if transition.new_status == RunStatus.PENDING:
        run_metrics.increment_pending_runs(run_model.project.name, run_spec.configuration.type)
        # Unassign run from fleet so that the new fleet can be chosen when retrying
        run_model.fleet = None

    run_model.termination_reason = transition.termination_reason
    switch_run_status(session=session, run_model=run_model, new_status=transition.new_status)
    # While a run goes to pending without provisioning, resubmission_attempt increases.
    if transition.new_status == RunStatus.PROVISIONING:
        run_model.resubmission_attempt = 0
    elif transition.new_status == RunStatus.PENDING:
        run_model.resubmission_attempt += 1


def _get_replica_info(
    replica_job_models: list[JobModel],
    replica_active: bool,
) -> autoscalers.ReplicaInfo:
    if replica_active:
        # submitted_at = replica created
        return autoscalers.ReplicaInfo(
            active=True,
            timestamp=min(job.submitted_at for job in replica_job_models),
        )
    # last_processed_at = replica scaled down
    return autoscalers.ReplicaInfo(
        active=False,
        timestamp=max(job.last_processed_at for job in replica_job_models),
    )


async def _handle_run_replicas(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
    replicas_to_retry: list[tuple[int, list[JobModel]]],
    retry_single_job: bool,
    replicas_info: list[autoscalers.ReplicaInfo],
) -> None:
    """
    Performs one or more steps:
    - replicas retry
    - replicas scaling
    - replicas rolling deployment
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
        replica_groups: List[ReplicaGroup] = run_spec.configuration.replica_groups
        assert replica_groups, "replica groups should always return at least one group"

        await scale_run_replicas_for_all_groups(session, run_model, replica_groups)

        await _update_jobs_to_new_deployment_in_place(
            session=session,
            run_model=run_model,
            run_spec=run_spec,
        )

        for group in replica_groups:
            await _handle_rolling_deployment_for_group(
                session=session, run_model=run_model, group=group, run_spec=run_spec
            )

        _terminate_removed_replica_groups(
            session=session, run_model=run_model, replica_groups=replica_groups
        )
        return

    await _update_jobs_to_new_deployment_in_place(
        session=session,
        run_model=run_model,
        run_spec=run_spec,
    )
    if has_out_of_date_replicas(run_model):
        # Currently, only services can change job spec on update,
        # so for other runs out-of-date replicas are not possible.
        # Keeping assert in case this changes.
        assert False, "Rolling deployment is only supported for services"


async def _update_jobs_to_new_deployment_in_place(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
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

        replica_group_name = None
        if run_spec.configuration.type == "service":
            job_spec = get_job_spec(job_models[0])
            replica_group_name = job_spec.replica_group

        # FIXME: Handle getting image configuration errors or skip it.
        new_job_specs = await get_job_specs_from_run_spec(
            run_spec=run_spec,
            secrets=secrets,
            replica_num=replica_num,
            replica_group_name=replica_group_name,
        )
        assert len(new_job_specs) == len(job_models), (
            "Changing the number of jobs within a replica is not yet supported"
        )
        can_update_all_jobs = True
        for old_job_model, new_job_spec in zip(job_models, new_job_specs):
            old_job_spec = get_job_spec(old_job_model)
            if new_job_spec != old_job_spec:
                can_update_all_jobs = False
                break
        if can_update_all_jobs:
            for job_model in job_models:
                job_model.deployment_num = run_model.deployment_num
                events.emit(
                    session,
                    f"Job updated. Deployment: {job_model.deployment_num}",
                    actor=events.SystemActor(),
                    targets=[events.Target.from_model(job_model)],
                )


async def _should_retry_job(
    session: AsyncSession,
    run: Run,
    job: Job,
    job_model: JobModel,
) -> Optional[datetime.timedelta]:
    """
    Checks if the job should be retried.
    Returns the current duration of retrying if retry is enabled.
    Retrying duration is calculated as the time since `last_processed_at`
    of the latest provisioned submission.
    """
    if job.job_spec.retry is None:
        return None

    last_provisioned_submission = None
    if len(job.job_submissions) > 0:
        last_submission = job.job_submissions[-1]
        if last_submission.job_provisioning_data is not None:
            last_provisioned_submission = last_submission
        else:
            # The caller passes at most one latest submission in job.job_submissions, so check the db.
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.run_id == job_model.run_id,
                    JobModel.replica_num == job_model.replica_num,
                    JobModel.job_num == job_model.job_num,
                    JobModel.job_provisioning_data.is_not(None),
                )
                .order_by(JobModel.last_processed_at.desc())
                .limit(1)
            )
            last_provisioned_submission_model = res.scalar()
            if last_provisioned_submission_model is not None:
                last_provisioned_submission = job_model_to_job_submission(
                    last_provisioned_submission_model
                )

    if (
        job_model.termination_reason is not None
        and job_model.termination_reason.to_retry_event() == RetryEvent.NO_CAPACITY
        and last_provisioned_submission is None
        and RetryEvent.NO_CAPACITY in job.job_spec.retry.on_events
    ):
        return common.get_current_datetime() - run.submitted_at

    if (
        job_model.termination_reason is not None
        and job_model.termination_reason.to_retry_event() in job.job_spec.retry.on_events
        and last_provisioned_submission is not None
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
        if is_master_job(job) and job.job_submissions[-1].status == JobStatus.DONE:
            return True
    return False


async def _handle_rolling_deployment_for_group(
    session: AsyncSession, run_model: RunModel, group: ReplicaGroup, run_spec: RunSpec
) -> None:
    """
    Handle rolling deployment for a single replica group.
    """
    if not has_out_of_date_replicas(run_model, group_filter=group.name):
        return

    desired_replica_counts = (
        json.loads(run_model.desired_replica_counts) if run_model.desired_replica_counts else {}
    )
    group_desired = desired_replica_counts.get(group.name, group.count.min or 0)
    group_max_replica_count = group_desired + ROLLING_DEPLOYMENT_MAX_SURGE

    non_terminated_replica_count = len(
        {
            j.replica_num
            for j in run_model.jobs
            if not j.status.is_finished()
            and group.name is not None
            and job_belongs_to_group(job=j, group_name=group.name)
        }
    )

    # Start new up-to-date replicas if needed
    if non_terminated_replica_count < group_max_replica_count:
        active_replicas, inactive_replicas = build_replica_lists(
            run_model=run_model,
            group_filter=group.name,
        )

        await scale_run_replicas_for_group(
            session=session,
            run_model=run_model,
            group=group,
            replicas_diff=group_max_replica_count - non_terminated_replica_count,
            run_spec=run_spec,
            active_replicas=active_replicas,
            inactive_replicas=inactive_replicas,
        )

    # Stop out-of-date replicas that are not registered
    replicas_to_stop_count = 0
    for _, jobs in group_jobs_by_replica_latest(run_model.jobs):
        assert group.name is not None, "Group name is always set"
        if not job_belongs_to_group(jobs[0], group.name):
            continue
        # Check if replica is out-of-date and not registered
        if (
            any(j.deployment_num < run_model.deployment_num for j in jobs)
            and any(
                j.status not in [JobStatus.TERMINATING] + JobStatus.finished_statuses()
                for j in jobs
            )
            and not is_replica_registered(jobs)
        ):
            replicas_to_stop_count += 1

    # Stop excessive registered out-of-date replicas
    non_terminating_registered_replicas_count = 0
    for _, jobs in group_jobs_by_replica_latest(run_model.jobs):
        assert group.name is not None, "Group name is always set"
        if not job_belongs_to_group(jobs[0], group.name):
            continue

        if is_replica_registered(jobs) and all(j.status != JobStatus.TERMINATING for j in jobs):
            non_terminating_registered_replicas_count += 1

    replicas_to_stop_count += max(0, non_terminating_registered_replicas_count - group_desired)

    if replicas_to_stop_count > 0:
        # Build lists again to get current state
        active_replicas, inactive_replicas = build_replica_lists(
            run_model=run_model,
            group_filter=group.name,
        )

        await scale_run_replicas_for_group(
            session=session,
            run_model=run_model,
            group=group,
            replicas_diff=-replicas_to_stop_count,
            run_spec=run_spec,
            active_replicas=active_replicas,
            inactive_replicas=inactive_replicas,
        )


def _terminate_removed_replica_groups(
    session: AsyncSession, run_model: RunModel, replica_groups: List[ReplicaGroup]
):
    existing_group_names = set()
    for job in run_model.jobs:
        if job.status.is_finished():
            continue
        job_spec = get_job_spec(job)
        existing_group_names.add(job_spec.replica_group)
    new_group_names = {group.name for group in replica_groups}
    removed_group_names = existing_group_names - new_group_names
    for removed_group_name in removed_group_names:
        active_replicas, inactive_replicas = build_replica_lists(
            run_model=run_model,
            group_filter=removed_group_name,
        )
        total_replicas = len(active_replicas) + len(inactive_replicas)
        if total_replicas > 0:
            logger.info(
                "%s: terminating %d replica(s) from removed group '%s'",
                fmt(run_model),
                total_replicas,
                removed_group_name,
            )
            if active_replicas:
                scale_down_replicas(session, active_replicas, len(active_replicas))
            if inactive_replicas:
                scale_down_replicas(session, inactive_replicas, len(inactive_replicas))
