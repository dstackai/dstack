import itertools
import math
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import List, Optional

import pydantic
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

import dstack._internal.utils.common as common_utils
from dstack._internal.core.errors import (
    RepoDoesNotExistError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.profiles import (
    RetryEvent,
)
from dstack._internal.core.models.runs import (
    ApplyRunPlanInput,
    Job,
    JobSpec,
    JobStatus,
    JobSubmission,
    JobTerminationReason,
    ProbeSpec,
    Run,
    RunFleet,
    RunPlan,
    RunSpec,
    RunStatus,
    RunTerminationReason,
    ServiceSpec,
)
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    FleetModel,
    JobModel,
    ProbeModel,
    ProjectModel,
    RepoModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services import events, services
from dstack._internal.server.services import repos as repos_services
from dstack._internal.server.services.jobs import (
    check_can_attach_job_volumes,
    delay_job_instance_termination,
    get_job_configured_volumes,
    get_jobs_from_run_spec,
    job_model_to_job_submission,
    remove_job_spec_sensitive_info,
    stop_runner,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker, string_to_lock_id
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.plugins import apply_plugin_policies
from dstack._internal.server.services.probes import is_probe_ready
from dstack._internal.server.services.projects import list_user_project_models
from dstack._internal.server.services.resources import set_resources_defaults
from dstack._internal.server.services.runs.plan import get_job_plans
from dstack._internal.server.services.runs.spec import (
    can_update_run_spec,
    check_can_update_run_spec,
    validate_run_spec_and_set_defaults,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.server.services.users import get_user_model_by_name
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.random_names import generate_name

logger = get_logger(__name__)


JOB_TERMINATION_REASONS_TO_RETRY = {
    JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
}


def switch_run_status(
    session: AsyncSession,
    run_model: RunModel,
    new_status: RunStatus,
    actor: events.AnyActor = events.SystemActor(),
):
    """
    Switch run status.
    """
    old_status = run_model.status
    if old_status == new_status:
        return

    run_model.status = new_status

    msg = f"Run status changed {old_status.upper()} -> {new_status.upper()}"
    if new_status == RunStatus.TERMINATING:
        if run_model.termination_reason is None:
            raise ValueError("termination_reason must be set when switching to TERMINATING status")
        msg += f". Termination reason: {run_model.termination_reason.upper()}"
    events.emit(session, msg, actor=actor, targets=[events.Target.from_model(run_model)])


async def list_user_runs(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    repo_id: Optional[str],
    username: Optional[str],
    only_active: bool,
    include_jobs: bool,
    job_submissions_limit: Optional[int],
    prev_submitted_at: Optional[datetime],
    prev_run_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Run]:
    if project_name is None and repo_id is not None:
        return []
    projects = await list_user_project_models(
        session=session,
        user=user,
        only_names=True,
    )
    runs_user = None
    if username is not None:
        runs_user = await get_user_model_by_name(session=session, username=username)
        if runs_user is None:
            raise ResourceNotExistsError("User not found")
    repo = None
    if project_name is not None:
        projects = [p for p in projects if p.name == project_name]
        if len(projects) == 0:
            return []
        if repo_id is not None:
            repo = await repos_services.get_repo_model(
                session=session,
                project=projects[0],
                repo_id=repo_id,
            )
            if repo is None:
                raise RepoDoesNotExistError.with_id(repo_id)
    run_models = await list_projects_run_models(
        session=session,
        projects=projects,
        repo=repo,
        runs_user=runs_user,
        only_active=only_active,
        prev_submitted_at=prev_submitted_at,
        prev_run_id=prev_run_id,
        limit=limit,
        ascending=ascending,
    )
    runs = []
    for r in run_models:
        try:
            runs.append(
                run_model_to_run(
                    r,
                    return_in_api=True,
                    include_jobs=include_jobs,
                    job_submissions_limit=job_submissions_limit,
                )
            )
        except pydantic.ValidationError:
            pass
    if len(run_models) > len(runs):
        logger.debug("Can't load %s runs", len(run_models) - len(runs))
    return runs


async def list_projects_run_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    repo: Optional[RepoModel],
    runs_user: Optional[UserModel],
    only_active: bool,
    prev_submitted_at: Optional[datetime],
    prev_run_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[RunModel]:
    filters = []
    filters.append(RunModel.project_id.in_(p.id for p in projects))
    if repo is not None:
        filters.append(RunModel.repo_id == repo.id)
    if runs_user is not None:
        filters.append(RunModel.user_id == runs_user.id)
    if only_active:
        filters.append(RunModel.status.not_in(RunStatus.finished_statuses()))
    if prev_submitted_at is not None:
        if ascending:
            if prev_run_id is None:
                filters.append(RunModel.submitted_at > prev_submitted_at)
            else:
                filters.append(
                    or_(
                        RunModel.submitted_at > prev_submitted_at,
                        and_(
                            RunModel.submitted_at == prev_submitted_at, RunModel.id < prev_run_id
                        ),
                    )
                )
        else:
            if prev_run_id is None:
                filters.append(RunModel.submitted_at < prev_submitted_at)
            else:
                filters.append(
                    or_(
                        RunModel.submitted_at < prev_submitted_at,
                        and_(
                            RunModel.submitted_at == prev_submitted_at, RunModel.id > prev_run_id
                        ),
                    )
                )
    order_by = (RunModel.submitted_at.desc(), RunModel.id)
    if ascending:
        order_by = (RunModel.submitted_at.asc(), RunModel.id.desc())

    res = await session.execute(
        select(RunModel)
        .where(*filters)
        .options(joinedload(RunModel.user).load_only(UserModel.name))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
        .options(selectinload(RunModel.jobs).joinedload(JobModel.probes))
        .order_by(*order_by)
        .limit(limit)
    )
    run_models = list(res.scalars().all())
    return run_models


async def get_run(
    session: AsyncSession,
    project: ProjectModel,
    run_name: Optional[str] = None,
    run_id: Optional[uuid.UUID] = None,
) -> Optional[Run]:
    if run_id is not None:
        return await get_run_by_id(
            session=session,
            project=project,
            run_id=run_id,
        )
    elif run_name is not None:
        return await get_run_by_name(
            session=session,
            project=project,
            run_name=run_name,
        )
    raise ServerClientError("run_name or id must be specified")


async def get_run_by_name(
    session: AsyncSession,
    project: ProjectModel,
    run_name: str,
) -> Optional[Run]:
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.project_id == project.id,
            RunModel.run_name == run_name,
            RunModel.deleted == False,
        )
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
        .options(selectinload(RunModel.jobs).joinedload(JobModel.probes))
    )
    run_model = res.scalar()
    if run_model is None:
        return None
    return run_model_to_run(run_model, return_in_api=True)


async def get_run_by_id(
    session: AsyncSession,
    project: ProjectModel,
    run_id: uuid.UUID,
) -> Optional[Run]:
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.project_id == project.id,
            RunModel.id == run_id,
        )
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
        .options(selectinload(RunModel.jobs).joinedload(JobModel.probes))
    )
    run_model = res.scalar()
    if run_model is None:
        return None
    return run_model_to_run(run_model, return_in_api=True)


async def get_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    run_spec: RunSpec,
    max_offers: Optional[int],
    legacy_repo_dir: bool = False,
) -> RunPlan:
    # Spec must be copied by parsing to calculate merged_profile
    effective_run_spec = RunSpec.parse_obj(run_spec.dict())
    effective_run_spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=effective_run_spec,
    )
    effective_run_spec = RunSpec.parse_obj(effective_run_spec.dict())
    validate_run_spec_and_set_defaults(
        user=user,
        run_spec=effective_run_spec,
        legacy_repo_dir=legacy_repo_dir,
    )
    profile = effective_run_spec.merged_profile

    current_resource = None
    action = ApplyAction.CREATE
    if effective_run_spec.run_name is not None:
        current_resource = await get_run_by_name(
            session=session,
            project=project,
            run_name=effective_run_spec.run_name,
        )
        if current_resource is not None:
            # For backward compatibility (current_resource may has been submitted before
            # some fields, e.g., CPUSpec.arch, were added)
            set_resources_defaults(current_resource.run_spec.configuration.resources)
            if not current_resource.status.is_finished() and can_update_run_spec(
                current_resource.run_spec, effective_run_spec
            ):
                action = ApplyAction.UPDATE

    job_plans = await get_job_plans(
        session=session,
        project=project,
        profile=profile,
        run_spec=run_spec,
        max_offers=max_offers,
    )
    run_plan = RunPlan(
        project_name=project.name,
        user=user.name,
        run_spec=run_spec,
        effective_run_spec=effective_run_spec,
        job_plans=job_plans,
        current_resource=current_resource,
        action=action,
    )
    return run_plan


async def apply_plan(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    plan: ApplyRunPlanInput,
    force: bool,
    legacy_repo_dir: bool = False,
) -> Run:
    run_spec = plan.run_spec
    run_spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        spec=run_spec,
    )
    # Spec must be copied by parsing to calculate merged_profile
    run_spec = RunSpec.parse_obj(run_spec.dict())
    validate_run_spec_and_set_defaults(
        user=user, run_spec=run_spec, legacy_repo_dir=legacy_repo_dir
    )
    if run_spec.run_name is None:
        return await submit_run(
            session=session,
            user=user,
            project=project,
            run_spec=run_spec,
        )
    current_resource = await get_run_by_name(
        session=session,
        project=project,
        run_name=run_spec.run_name,
    )
    if current_resource is None or current_resource.status.is_finished():
        return await submit_run(
            session=session,
            user=user,
            project=project,
            run_spec=run_spec,
        )

    # For backward compatibility (current_resource may has been submitted before
    # some fields, e.g., CPUSpec.arch, were added)
    set_resources_defaults(current_resource.run_spec.configuration.resources)
    try:
        check_can_update_run_spec(current_resource.run_spec, run_spec)
    except ServerClientError:
        # The except is only needed to raise an appropriate error if run is active
        if not current_resource.status.is_finished():
            raise ServerClientError("Cannot override active run. Stop the run first.")
        raise
    if not force:
        if plan.current_resource is not None:
            set_resources_defaults(plan.current_resource.run_spec.configuration.resources)
        if (
            plan.current_resource is None
            or plan.current_resource.id != current_resource.id
            or plan.current_resource.run_spec != current_resource.run_spec
        ):
            raise ServerClientError(
                "Failed to apply plan. Resource has been changed. Try again or use force apply."
            )
    # FIXME: potentially long write transaction
    # Avoid getting run_model after update
    await session.execute(
        update(RunModel)
        .where(RunModel.id == current_resource.id)
        .values(
            run_spec=run_spec.json(),
            priority=run_spec.configuration.priority,
            deployment_num=current_resource.deployment_num + 1,
        )
    )
    run = await get_run_by_name(
        session=session,
        project=project,
        run_name=run_spec.run_name,
    )
    return common_utils.get_or_error(run)


async def submit_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
) -> Run:
    validate_run_spec_and_set_defaults(user, run_spec)
    repo = await _get_run_repo_or_error(
        session=session,
        project=project,
        run_spec=run_spec,
    )
    secrets = await get_project_secrets_mapping(
        session=session,
        project=project,
    )

    lock_namespace = f"run_names_{project.name}"
    if is_db_sqlite():
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
        # FIXME: delete_runs commits, so Postgres lock is released too early.
        if run_spec.run_name is None:
            run_spec.run_name = await _generate_run_name(
                session=session,
                project=project,
            )
        else:
            await delete_runs(
                session=session, user=user, project=project, runs_names=[run_spec.run_name]
            )

        await _validate_run(
            session=session,
            user=user,
            project=project,
            run_spec=run_spec,
        )

        submitted_at = common_utils.get_current_datetime()
        initial_status = RunStatus.SUBMITTED
        initial_replicas = 1
        if run_spec.merged_profile.schedule is not None:
            initial_status = RunStatus.PENDING
            initial_replicas = 0
        elif run_spec.configuration.type == "service":
            initial_replicas = run_spec.configuration.replicas.min or 0

        run_model = RunModel(
            id=uuid.uuid4(),
            project_id=project.id,
            project=project,
            repo_id=repo.id,
            user_id=user.id,
            run_name=run_spec.run_name,
            submitted_at=submitted_at,
            status=initial_status,
            run_spec=run_spec.json(),
            last_processed_at=submitted_at,
            priority=run_spec.configuration.priority,
            deployment_num=0,
            desired_replica_count=1,  # a relevant value will be set in process_runs.py
            next_triggered_at=_get_next_triggered_at(run_spec),
        )
        session.add(run_model)
        events.emit(
            session,
            f"Run submitted. Status: {run_model.status.upper()}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run_model)],
        )

        if run_spec.configuration.type == "service":
            await services.register_service(session, run_model, run_spec)

        for replica_num in range(initial_replicas):
            jobs = await get_jobs_from_run_spec(
                run_spec=run_spec,
                secrets=secrets,
                replica_num=replica_num,
            )
            for job in jobs:
                job_model = create_job_model_for_new_submission(
                    run_model=run_model,
                    job=job,
                    status=JobStatus.SUBMITTED,
                )
                session.add(job_model)
                events.emit(
                    session,
                    f"Job created on run submission. Status: {job_model.status.upper()}",
                    # Set `SystemActor` for consistency with all other places where jobs can be
                    # created (retry, scaling, rolling deployments, etc). Think of the run as being
                    # created by the user, while the job is created by the system to satisfy the
                    # run spec.
                    actor=events.SystemActor(),
                    targets=[
                        events.Target.from_model(job_model),
                    ],
                )
        await session.commit()
        await session.refresh(run_model)

        run = await get_run_by_id(session, project, run_model.id)
        return common_utils.get_or_error(run)


def create_job_model_for_new_submission(
    run_model: RunModel,
    job: Job,
    status: JobStatus,
) -> JobModel:
    """
    Create a new job.

    **NOTE**: don't forget to emit an event when writing the new job to the database.
    """
    now = common_utils.get_current_datetime()
    return JobModel(
        id=uuid.uuid4(),
        project_id=run_model.project_id,
        run_id=run_model.id,
        run_name=run_model.run_name,
        job_num=job.job_spec.job_num,
        job_name=f"{job.job_spec.job_name}",
        replica_num=job.job_spec.replica_num,
        deployment_num=run_model.deployment_num,
        submission_num=len(job.job_submissions),
        submitted_at=now,
        last_processed_at=now,
        status=status,
        termination_reason=None,
        job_spec_data=job.job_spec.json(),
        job_provisioning_data=None,
        probes=[],
        waiting_master_job=job.job_spec.job_num != 0,
    )


async def stop_runs(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    runs_names: List[str],
    abort: bool,
):
    """
    If abort is False, jobs receive a signal to stop and run status will be changed as a reaction to jobs status change.
    If abort is True, run is marked as TERMINATED and process_runs will stop the jobs.
    """
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id,
            RunModel.run_name.in_(runs_names),
            RunModel.status.not_in(RunStatus.finished_statuses()),
        )
    )
    run_models = res.scalars().all()
    run_ids = sorted([r.id for r in run_models])
    await session.commit()
    async with get_locker(get_db().dialect_name).lock_ctx(RunModel.__tablename__, run_ids):
        res = await session.execute(
            select(RunModel)
            .where(RunModel.id.in_(run_ids))
            .order_by(RunModel.id)  # take locks in order
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        run_models = res.scalars().all()
        now = common_utils.get_current_datetime()
        for run_model in run_models:
            if run_model.status.is_finished():
                continue
            if abort:
                run_model.termination_reason = RunTerminationReason.ABORTED_BY_USER
            else:
                run_model.termination_reason = RunTerminationReason.STOPPED_BY_USER
            switch_run_status(
                session, run_model, RunStatus.TERMINATING, actor=events.UserActor.from_user(user)
            )
            run_model.last_processed_at = now
            # The run will be terminated by process_runs.
            # Terminating synchronously is problematic since it may take a long time.
        await session.commit()


async def delete_runs(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    runs_names: List[str],
):
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id,
            RunModel.run_name.in_(runs_names),
        )
    )
    run_models = res.scalars().all()
    run_ids = sorted([r.id for r in run_models])
    await session.commit()
    async with get_locker(get_db().dialect_name).lock_ctx(RunModel.__tablename__, run_ids):
        res = await session.execute(
            select(RunModel)
            .where(RunModel.id.in_(run_ids))
            .order_by(RunModel.id)  # take locks in order
            .with_for_update(key_share=True)
        )
        run_models = res.scalars().all()
        active_runs = [r for r in run_models if not r.status.is_finished()]
        if len(active_runs) > 0:
            raise ServerClientError(
                msg=f"Cannot delete active runs: {[r.run_name for r in active_runs]}"
            )
        for run_model in run_models:
            if not run_model.deleted:
                run_model.deleted = True
                events.emit(
                    session,
                    "Run deleted",
                    actor=events.UserActor.from_user(user),
                    targets=[events.Target.from_model(run_model)],
                )
        await session.commit()


def run_model_to_run(
    run_model: RunModel,
    include_jobs: bool = True,
    job_submissions_limit: Optional[int] = None,
    return_in_api: bool = False,
    include_sensitive: bool = False,
) -> Run:
    jobs: List[Job] = []
    if include_jobs:
        jobs = _get_run_jobs_with_submissions(
            run_model=run_model,
            job_submissions_limit=job_submissions_limit,
            return_in_api=return_in_api,
            include_sensitive=include_sensitive,
        )

    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    latest_job_submission = None
    if len(jobs) > 0 and len(jobs[0].job_submissions) > 0:
        # TODO(egor-s): does it make sense with replicas and multi-node?
        latest_job_submission = jobs[0].job_submissions[-1]

    service_spec = None
    if run_model.service_spec is not None:
        service_spec = ServiceSpec.__response__.parse_raw(run_model.service_spec)

    status_message = _get_run_status_message(run_model)
    error = _get_run_error(run_model)
    fleet = _get_run_fleet(run_model)
    next_triggered_at = None
    if not run_model.status.is_finished():
        next_triggered_at = _get_next_triggered_at(run_spec)
    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        fleet=fleet,
        submitted_at=run_model.submitted_at,
        last_processed_at=run_model.last_processed_at,
        status=run_model.status,
        status_message=status_message,
        termination_reason=run_model.termination_reason.value
        if run_model.termination_reason
        else None,
        run_spec=run_spec,
        jobs=jobs,
        latest_job_submission=latest_job_submission,
        service=service_spec,
        deployment_num=run_model.deployment_num,
        error=error,
        deleted=run_model.deleted,
        next_triggered_at=next_triggered_at,
    )
    run.cost = _get_run_cost(run)
    return run


def _get_run_jobs_with_submissions(
    run_model: RunModel,
    job_submissions_limit: Optional[int],
    return_in_api: bool = False,
    include_sensitive: bool = False,
) -> List[Job]:
    jobs: List[Job] = []
    run_jobs = sorted(run_model.jobs, key=lambda j: (j.replica_num, j.job_num, j.submission_num))
    for replica_num, replica_submissions in itertools.groupby(
        run_jobs, key=lambda j: j.replica_num
    ):
        for job_num, job_models in itertools.groupby(replica_submissions, key=lambda j: j.job_num):
            submissions = []
            job_model = None
            if job_submissions_limit is not None:
                if job_submissions_limit == 0:
                    # Take latest job submission to return its job_spec
                    job_models = list(job_models)[-1:]
                else:
                    job_models = list(job_models)[-job_submissions_limit:]
            for job_model in job_models:
                if job_submissions_limit != 0:
                    job_submission = job_model_to_job_submission(
                        job_model, include_probes=return_in_api
                    )
                    if return_in_api:
                        # Set default non-None values for 0.18 backward-compatibility
                        # Remove in 0.19
                        if job_submission.job_provisioning_data is not None:
                            if job_submission.job_provisioning_data.hostname is None:
                                job_submission.job_provisioning_data.hostname = ""
                            if job_submission.job_provisioning_data.ssh_port is None:
                                job_submission.job_provisioning_data.ssh_port = 22
                    submissions.append(job_submission)
            if job_model is not None:
                # Use the spec from the latest submission. Submissions can have different specs
                job_spec = JobSpec.__response__.parse_raw(job_model.job_spec_data)
                if not include_sensitive:
                    remove_job_spec_sensitive_info(job_spec)
                jobs.append(Job(job_spec=job_spec, job_submissions=submissions))
    return jobs


def _get_run_status_message(run_model: RunModel) -> str:
    if len(run_model.jobs) == 0:
        return run_model.status.value

    sorted_job_models = sorted(
        run_model.jobs, key=lambda j: (j.replica_num, j.job_num, j.submission_num)
    )
    job_models_grouped_by_job = list(
        list(jm)
        for _, jm in itertools.groupby(sorted_job_models, key=lambda j: (j.replica_num, j.job_num))
    )

    if all(job_models[-1].status == JobStatus.PULLING for job_models in job_models_grouped_by_job):
        # Show `pulling`` if last job submission of all jobs is pulling
        return "pulling"

    if run_model.status in [RunStatus.SUBMITTED, RunStatus.PENDING]:
        # Show `retrying` if any job caused the run to retry
        for job_models in job_models_grouped_by_job:
            last_job_spec = JobSpec.__response__.parse_raw(job_models[-1].job_spec_data)
            retry_on_events = last_job_spec.retry.on_events if last_job_spec.retry else []
            last_job_termination_reason = _get_last_job_termination_reason(job_models)
            if (
                last_job_termination_reason
                == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
                and RetryEvent.NO_CAPACITY in retry_on_events
            ):
                # TODO: Show `retrying` for other retry events
                return "retrying"

    return run_model.status.value


def _get_last_job_termination_reason(job_models: List[JobModel]) -> Optional[JobTerminationReason]:
    for job_model in reversed(job_models):
        if job_model.termination_reason is not None:
            return job_model.termination_reason
    return None


def _get_run_error(run_model: RunModel) -> Optional[str]:
    if run_model.termination_reason is None:
        return None
    return run_model.termination_reason.to_error()


def _get_run_fleet(run_model: RunModel) -> Optional[RunFleet]:
    if run_model.fleet is None:
        return None
    return RunFleet(
        id=run_model.fleet.id,
        name=run_model.fleet.name,
    )


async def _generate_run_name(
    session: AsyncSession,
    project: ProjectModel,
) -> str:
    run_name_base = generate_name()
    idx = 1
    while True:
        res = await session.execute(
            select(RunModel).where(
                RunModel.project_id == project.id,
                RunModel.run_name == f"{run_name_base}-{idx}",
                RunModel.deleted == False,
            )
        )
        run_model = res.scalar()
        if run_model is None:
            return f"{run_name_base}-{idx}"
        idx += 1


async def _validate_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
):
    await _validate_run_volumes(
        session=session,
        project=project,
        run_spec=run_spec,
    )


async def _validate_run_volumes(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
):
    # The volumes validation should be done here and not in job configurator
    # since potentially we may need to validate volumes for jobs/replicas
    # that won't be created immediately (e.g. range of replicas or nodes).
    nodes = 1
    if run_spec.configuration.type == "task":
        nodes = run_spec.configuration.nodes
    for job_num in range(nodes):
        volumes = await get_job_configured_volumes(
            session=session, project=project, run_spec=run_spec, job_num=job_num
        )
        check_can_attach_job_volumes(volumes=volumes)


async def _get_run_repo_or_error(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
) -> RepoModel:
    # Must be set by _validate_run_spec_and_set_defaults()
    repo_id = common_utils.get_or_error(run_spec.repo_id)
    repo_data = common_utils.get_or_error(run_spec.repo_data)
    if repo_data.repo_type == "virtual":
        repo = await repos_services.create_or_update_repo(
            session=session,
            project=project,
            repo_id=repo_id,
            repo_info=repo_data,
        )
    repo = await repos_services.get_repo_model(
        session=session,
        project=project,
        repo_id=repo_id,
    )
    if repo is None:
        raise RepoDoesNotExistError.with_id(repo_id)
    return repo


def _get_run_cost(run: Run) -> float:
    run_cost = math.fsum(
        _get_job_submission_cost(submission)
        for job in run.jobs
        for submission in job.job_submissions
    )
    return round(run_cost, 4)


def _get_job_submission_cost(job_submission: JobSubmission) -> float:
    if job_submission.job_provisioning_data is None:
        return 0
    duration_hours = job_submission.duration.total_seconds() / 3600
    return job_submission.job_provisioning_data.price * duration_hours


async def process_terminating_run(session: AsyncSession, run_model: RunModel):
    """
    Used by both `process_runs` and `stop_run` to process a TERMINATING run.
    Stops the jobs gracefully and marks them as TERMINATING.
    Jobs should be terminated by `process_terminating_jobs`.
    When all jobs are terminated, assigns a finished status to the run.
    Caller must acquire the lock on run.
    """
    assert run_model.termination_reason is not None
    run = run_model_to_run(run_model, include_jobs=False)
    job_termination_reason = run_model.termination_reason.to_job_termination_reason()

    unfinished_jobs_count = 0
    for job_model in run_model.jobs:
        if job_model.status.is_finished():
            continue
        unfinished_jobs_count += 1
        if job_model.status == JobStatus.TERMINATING:
            if job_termination_reason == JobTerminationReason.ABORTED_BY_USER:
                # Override termination reason so that
                # abort actions such as volume force detach are triggered
                job_model.termination_reason = job_termination_reason
            continue

        if job_model.status == JobStatus.RUNNING and job_termination_reason not in {
            JobTerminationReason.ABORTED_BY_USER,
            JobTerminationReason.DONE_BY_RUNNER,
        }:
            # Send a signal to stop the job gracefully
            await stop_runner(session, job_model)
            delay_job_instance_termination(job_model)
        job_model.termination_reason = job_termination_reason
        switch_job_status(session, job_model, JobStatus.TERMINATING)
        job_model.last_processed_at = common_utils.get_current_datetime()

    if unfinished_jobs_count == 0:
        if run_model.service_spec is not None:
            try:
                await services.unregister_service(session, run_model)
            except Exception as e:
                logger.warning("%s: failed to unregister service: %s", fmt(run_model), repr(e))
        if (
            run.run_spec.merged_profile.schedule is not None
            and run_model.termination_reason
            not in [RunTerminationReason.ABORTED_BY_USER, RunTerminationReason.STOPPED_BY_USER]
        ):
            run_model.next_triggered_at = _get_next_triggered_at(run.run_spec)
            switch_run_status(session, run_model, RunStatus.PENDING)
            # Unassign run from fleet so that the new fleet can be chosen on the next submission
            run_model.fleet = None
        else:
            switch_run_status(session, run_model, run_model.termination_reason.to_status())


def is_job_ready(probes: Iterable[ProbeModel], probe_specs: Iterable[ProbeSpec]) -> bool:
    return all(is_probe_ready(probe, probe_spec) for probe, probe_spec in zip(probes, probe_specs))


def _get_next_triggered_at(run_spec: RunSpec) -> Optional[datetime]:
    if run_spec.merged_profile.schedule is None:
        return None
    now = common_utils.get_current_datetime()
    fire_times = []
    for cron in run_spec.merged_profile.schedule.crons:
        cron_trigger = CronTrigger.from_crontab(cron, timezone=timezone.utc)
        fire_times.append(
            cron_trigger.get_next_fire_time(
                previous_fire_time=None,
                now=now,
            )
        )
    return min(fire_times)
