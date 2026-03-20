"""Active-run analysis and transition helpers for the run pipeline."""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import load_only

from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.profiles import RetryEvent, StopCriteria
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.background.pipeline_tasks.base import ItemUpdateMap
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import (
    get_job_spec,
    get_job_specs_from_run_spec,
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
)
from dstack._internal.server.services.runs import create_job_model_for_new_submission
from dstack._internal.server.services.runs.replicas import has_out_of_date_replicas
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class ActiveRunUpdateMap(ItemUpdateMap, total=False):
    status: RunStatus
    termination_reason: Optional[RunTerminationReason]
    fleet_id: Optional[uuid.UUID]
    resubmission_attempt: int


class ActiveRunJobUpdateMap(ItemUpdateMap, total=False):
    status: JobStatus
    termination_reason: Optional[JobTerminationReason]
    termination_reason_message: Optional[str]
    deployment_num: int


@dataclass
class ActiveContext:
    run_model: RunModel
    run_spec: RunSpec
    secrets: dict
    locked_job_models: list[JobModel]


@dataclass
class ActiveResult:
    run_update_map: ActiveRunUpdateMap
    new_job_models: list[JobModel]
    job_id_to_update_map: dict[uuid.UUID, ActiveRunJobUpdateMap]


@dataclass
class _ReplicaAnalysis:
    """Per-replica classification of job states for determining the run's next status."""

    replica_num: int
    job_models: List[JobModel]
    contributed_statuses: Set[RunStatus] = field(default_factory=set)
    """`RunStatus` values derived from this replica's jobs. Merged into the run-level
    analysis unless the replica is being retried as a whole."""
    termination_reasons: Set[RunTerminationReason] = field(default_factory=set)
    """Why the replica failed. Only populated when `FAILED` is in `contributed_statuses`."""
    needs_retry: bool = False
    """At least one job failed with a retryable reason and the retry duration hasn't been
    exceeded. When `True`, the replica does not contribute its statuses to the run-level
    analysis and is added to `replicas_to_retry` instead."""


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


@dataclass
class _ActiveRunTransition:
    new_status: RunStatus
    termination_reason: Optional[RunTerminationReason] = None


async def process_active_run(context: ActiveContext) -> ActiveResult:
    run_model = context.run_model
    run_spec = context.run_spec

    fleet_id = _detect_fleet_id_from_jobs(run_model)
    analysis = await _analyze_active_run(run_model)
    transition = _get_active_run_transition(run_spec, run_model, analysis)

    run_update_map = _build_run_update_map(run_model, run_spec, transition, fleet_id)
    new_job_models: list[JobModel] = []
    job_id_to_update_map: Dict[uuid.UUID, ActiveRunJobUpdateMap] = {}

    if transition.new_status == RunStatus.PENDING:
        job_id_to_update_map = _build_terminate_retrying_jobs_map(analysis.replicas_to_retry)
    elif transition.new_status not in {RunStatus.TERMINATING, RunStatus.PENDING}:
        if analysis.replicas_to_retry:
            new_job_models = await _build_retry_job_models(context, analysis.replicas_to_retry)
        else:
            job_id_to_update_map = await _build_deployment_update_map(context)

    return ActiveResult(
        run_update_map=run_update_map,
        new_job_models=new_job_models,
        job_id_to_update_map=job_id_to_update_map,
    )


def _detect_fleet_id_from_jobs(run_model: RunModel) -> Optional[uuid.UUID]:
    """Detect fleet_id from job instances. Returns the current fleet_id if already set."""
    if run_model.fleet_id is not None:
        return run_model.fleet_id
    for job_model in run_model.jobs:
        if job_model.instance is not None and job_model.instance.fleet_id is not None:
            return job_model.instance.fleet_id
    return None


async def _analyze_active_run(run_model: RunModel) -> _RunAnalysis:
    run_analysis = _RunAnalysis()
    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        replica_analysis = await _analyze_active_run_replica(
            run_model=run_model,
            replica_num=replica_num,
            job_models=job_models,
        )
        _apply_replica_analysis(run_analysis, replica_analysis)
    return run_analysis


async def _analyze_active_run_replica(
    run_model: RunModel,
    replica_num: int,
    job_models: List[JobModel],
) -> _ReplicaAnalysis:
    contributed_statuses: Set[RunStatus] = set()
    termination_reasons: Set[RunTerminationReason] = set()
    needs_retry = False

    for job_model in job_models:
        if _job_is_done_or_finishing_done(job_model):
            contributed_statuses.add(RunStatus.DONE)
            continue

        if _job_was_scaled_down(job_model):
            continue

        replica_status = _get_non_terminal_replica_status(job_model)
        if replica_status is not None:
            contributed_statuses.add(replica_status)
            continue

        if _job_needs_retry_evaluation(job_model):
            current_duration = await _should_retry_job(run_model, job_model)
            if current_duration is None:
                contributed_statuses.add(RunStatus.FAILED)
                termination_reasons.add(RunTerminationReason.JOB_FAILED)
            elif _is_retry_duration_exceeded(job_model, current_duration):
                contributed_statuses.add(RunStatus.FAILED)
                termination_reasons.add(RunTerminationReason.RETRY_LIMIT_EXCEEDED)
            else:
                needs_retry = True
            continue

        raise ServerError(f"Unexpected job status {job_model.status}")

    return _ReplicaAnalysis(
        replica_num=replica_num,
        job_models=job_models,
        contributed_statuses=contributed_statuses,
        termination_reasons=termination_reasons,
        needs_retry=needs_retry,
    )


def _apply_replica_analysis(
    analysis: _RunAnalysis,
    replica_analysis: _ReplicaAnalysis,
) -> None:
    if RunStatus.FAILED in replica_analysis.contributed_statuses:
        analysis.contributed_statuses.add(RunStatus.FAILED)
        analysis.termination_reasons.update(replica_analysis.termination_reasons)
        return

    if replica_analysis.needs_retry:
        analysis.replicas_to_retry.append(
            (replica_analysis.replica_num, replica_analysis.job_models)
        )

    if not replica_analysis.needs_retry:
        analysis.contributed_statuses.update(replica_analysis.contributed_statuses)


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


async def _should_retry_job(
    run_model: RunModel,
    job_model: JobModel,
) -> Optional[timedelta]:
    """
    Checks if the job should be retried.
    Returns the current duration of retrying if retry is enabled.
    Retrying duration is calculated as the time since `last_processed_at`
    of the latest provisioned submission.
    """
    job_spec = get_job_spec(job_model)
    if job_spec.retry is None:
        return None

    last_provisioned = await _load_last_provisioned_job(
        run_id=job_model.run_id,
        replica_num=job_model.replica_num,
        job_num=job_model.job_num,
    )

    if (
        job_model.termination_reason is not None
        and job_model.termination_reason.to_retry_event() == RetryEvent.NO_CAPACITY
        and last_provisioned is None
        and RetryEvent.NO_CAPACITY in job_spec.retry.on_events
    ):
        return get_current_datetime() - run_model.submitted_at

    if (
        job_model.termination_reason is not None
        and job_model.termination_reason.to_retry_event() in job_spec.retry.on_events
        and last_provisioned is not None
    ):
        return get_current_datetime() - last_provisioned.last_processed_at

    return None


async def _load_last_provisioned_job(
    run_id: uuid.UUID,
    replica_num: int,
    job_num: int,
) -> Optional[JobModel]:
    """Load the last submission with provisioning data for a single (replica_num, job_num)."""
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel)
            .where(
                JobModel.run_id == run_id,
                JobModel.replica_num == replica_num,
                JobModel.job_num == job_num,
                JobModel.job_provisioning_data.is_not(None),
            )
            .order_by(JobModel.submission_num.desc())
            .limit(1)
            .options(load_only(JobModel.last_processed_at))
        )
        return res.scalar_one_or_none()


def _is_retry_duration_exceeded(job_model: JobModel, current_duration: timedelta) -> bool:
    job_spec = get_job_spec(job_model)
    if job_spec.retry is None:
        return True
    return current_duration > timedelta(seconds=job_spec.retry.duration)


def _should_stop_on_master_done(run_spec: RunSpec, run_model: RunModel) -> bool:
    if run_spec.merged_profile.stop_criteria != StopCriteria.MASTER_DONE:
        return False
    for job_model in run_model.jobs:
        if job_model.job_num == 0 and job_model.status == JobStatus.DONE:
            return True
    return False


def _get_active_run_transition(
    run_spec: RunSpec,
    run_model: RunModel,
    analysis: _RunAnalysis,
) -> _ActiveRunTransition:
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

    if _should_stop_on_master_done(run_spec, run_model):
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


def _build_run_update_map(
    run_model: RunModel,
    run_spec: RunSpec,
    transition: _ActiveRunTransition,
    fleet_id: Optional[uuid.UUID],
) -> ActiveRunUpdateMap:
    update_map = ActiveRunUpdateMap()

    if fleet_id != run_model.fleet_id:
        update_map["fleet_id"] = fleet_id

    if run_model.status == transition.new_status:
        return update_map

    update_map["status"] = transition.new_status
    update_map["termination_reason"] = transition.termination_reason

    if transition.new_status == RunStatus.PROVISIONING:
        update_map["resubmission_attempt"] = 0
    elif transition.new_status == RunStatus.PENDING:
        update_map["resubmission_attempt"] = run_model.resubmission_attempt + 1
        # Unassign run from fleet so that a new fleet can be chosen when retrying
        update_map["fleet_id"] = None

    return update_map


def _build_terminate_retrying_jobs_map(
    replicas_to_retry: List[Tuple[int, List[JobModel]]],
) -> dict[uuid.UUID, ActiveRunJobUpdateMap]:
    job_id_to_update_map: dict[uuid.UUID, ActiveRunJobUpdateMap] = {}
    for _, replica_jobs in replicas_to_retry:
        for job_model in replica_jobs:
            if job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING:
                continue
            job_id_to_update_map[job_model.id] = ActiveRunJobUpdateMap(
                status=JobStatus.TERMINATING,
                termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
                termination_reason_message="Run is to be resubmitted",
            )
    return job_id_to_update_map


async def _build_retry_job_models(
    context: ActiveContext,
    replicas_to_retry: List[Tuple[int, List[JobModel]]],
) -> list[JobModel]:
    new_job_models: list[JobModel] = []
    for _, replica_jobs in replicas_to_retry:
        job_spec = get_job_spec(replica_jobs[0])
        replica_group_name = job_spec.replica_group
        new_jobs = await get_jobs_from_run_spec(
            run_spec=context.run_spec,
            secrets=context.secrets,
            replica_num=replica_jobs[0].replica_num,
            replica_group_name=replica_group_name,
        )
        assert len(new_jobs) == len(replica_jobs), (
            "Changing the number of jobs within a replica is not yet supported"
        )
        for old_job_model, new_job in zip(replica_jobs, new_jobs):
            if not (
                old_job_model.status.is_finished() or old_job_model.status == JobStatus.TERMINATING
            ):
                # The job is not finished, but we have to retry all jobs. Terminate it.
                # This will be applied via the returned new_job_models only;
                # the caller should not also update these jobs via job_id_to_update_map.
                continue
            job_model = create_job_model_for_new_submission(
                run_model=context.run_model,
                job=new_job,
                status=JobStatus.SUBMITTED,
            )
            job_model.submission_num = old_job_model.submission_num + 1
            new_job_models.append(job_model)
    return new_job_models


async def _build_deployment_update_map(
    context: ActiveContext,
) -> dict[uuid.UUID, ActiveRunJobUpdateMap]:
    """Bump deployment_num for jobs that do not require redeployment."""
    run_model = context.run_model
    run_spec = context.run_spec
    job_id_to_update_map: dict[uuid.UUID, ActiveRunJobUpdateMap] = {}

    if not has_out_of_date_replicas(run_model):
        return job_id_to_update_map

    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        if all(j.status.is_finished() for j in job_models):
            continue
        if all(j.deployment_num == run_model.deployment_num for j in job_models):
            continue

        new_job_specs = await get_job_specs_from_run_spec(
            run_spec=run_spec,
            secrets=context.secrets,
            replica_num=replica_num,
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
                job_id_to_update_map[job_model.id] = ActiveRunJobUpdateMap(
                    deployment_num=run_model.deployment_num,
                )

    return job_id_to_update_map
