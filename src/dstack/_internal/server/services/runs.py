import asyncio
import uuid
from datetime import timezone
from typing import List, Optional

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.common as common_utils
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.runs import (
    Job,
    JobPlan,
    JobStatus,
    JobSubmission,
    Run,
    RunPlan,
    RunSpec,
)
from dstack._internal.server.models import JobModel, ProjectModel, RunModel, UserModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import repos
from dstack._internal.server.services.jobs import (
    get_jobs_from_run_spec,
    job_model_to_job_submission,
)
from dstack._internal.utils.random_names import generate_name


async def list_runs(
    session: AsyncSession,
    project: ProjectModel,
) -> List[Run]:
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id,
        )
    )
    run_models = res.scalars().all()
    return [run_model_to_run(r) for r in run_models]


async def get_run(
    session: AsyncSession,
    project: ProjectModel,
    run_name: str,
) -> Optional[Run]:
    res = await session.execute(
        select(RunModel).where(RunModel.project_id == project.id, RunModel.run_name == run_name)
    )
    run_model = res.scalar()
    if run_model is None:
        return None
    return run_model_to_run(run_model)


async def get_run_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    run_spec: RunSpec,
) -> RunPlan:
    backends = await backends_services.get_project_backends(project=project)
    run_spec.run_name = "dry-run"
    jobs = get_jobs_from_run_spec(run_spec)
    job_plans = []
    job = jobs[0]
    for job in jobs:
        candidates = await backends_services.get_instance_candidates(
            backends=backends,
            job=job,
            exclude_not_available=True,
        )
        job_plan = JobPlan(
            job_spec=job.job_spec,
            candidates=candidates[:50],
        )
        job_plans.append(job_plan)
    run_plan = RunPlan(
        project_name=project.name, user=user.name, run_spec=run_spec, job_plans=job_plans
    )
    return run_plan


async def submit_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
) -> Run:
    repo = await repos.get_repo_model(
        session=session,
        project=project,
        repo_id=run_spec.repo_id,
    )
    if repo is None:
        raise ServerClientError(f"Repo {run_spec.repo_id} does not exist")
    if run_spec.run_name is None:
        run_spec.run_name = await _generate_run_name(
            session=session,
            project=project,
        )
    run_model = RunModel(
        id=uuid.uuid4(),
        project=project,
        repo=repo,
        user=user,
        run_name=run_spec.run_name,
        submitted_at=common_utils.get_current_datetime(),
        status=JobStatus.SUBMITTED,
        run_spec=run_spec.json(),
    )
    session.add(run_model)
    jobs = get_jobs_from_run_spec(run_spec)
    for job in jobs:
        job_model = JobModel(
            id=uuid.uuid4(),
            project_id=project.id,
            run_id=run_model.id,
            run_name=run_spec.run_name,
            job_num=job.job_spec.job_num,
            job_name=job.job_spec.job_name,
            submission_num=0,
            submitted_at=run_model.submitted_at,
            last_processed_at=run_model.submitted_at,
            status=JobStatus.SUBMITTED,
            error_code=None,
            job_spec_data=job.job_spec.json(),
            job_provisioning_data=None,
        )
        session.add(job_model)
    await session.commit()
    await session.refresh(run_model)
    run = run_model_to_run(run_model)
    return run


async def stop_runs(
    session: AsyncSession,
    project: ProjectModel,
    runs_names: List[str],
    abort: bool,
):
    new_status = JobStatus.TERMINATED
    if abort:
        new_status = JobStatus.ABORTED
    # TODO stop instances
    await session.execute(
        update(JobModel)
        .where(
            JobModel.project_id == project.id,
            JobModel.run_name.in_(runs_names),
            JobModel.status.not_in(JobStatus.finished_statuses()),
        )
        .values(status=new_status)
    )


async def delete_runs(
    session: AsyncSession,
    project: ProjectModel,
    runs_names: List[str],
):
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id, RunModel.run_name.in_(runs_names)
        )
    )
    run_models = res.scalars().all()
    runs = [run_model_to_run(r) for r in run_models]
    active_runs = [r for r in runs if not r.status.is_finished()]
    if len(active_runs) > 0:
        raise ServerClientError(
            msg=f"Cannot delete active runs: {[r.run_spec.run_name for r in active_runs]}"
        )
    await session.execute(
        delete(RunModel).where(
            RunModel.project_id == project.id, RunModel.run_name.in_(runs_names)
        )
    )


def run_model_to_run(run_model: RunModel, include_job_submissions: bool = True) -> Run:
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    jobs = get_jobs_from_run_spec(run_spec)
    if include_job_submissions:
        for job_model in run_model.jobs:
            job = jobs[job_model.job_num]
            job_submission = job_model_to_job_submission(job_model)
            job.job_submissions.append(job_submission)
    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        submitted_at=run_model.submitted_at.replace(tzinfo=timezone.utc),
        status=get_run_status(jobs),
        run_spec=run_spec,
        jobs=jobs,
    )
    return run


def get_run_status(jobs: List[Job]) -> JobStatus:
    job = jobs[0]
    if len(job.job_submissions) == 0:
        return JobStatus.SUBMITTED
    return job.job_submissions[-1].status


_PROJECTS_TO_RUN_NAMES_LOCK = {}


async def _generate_run_name(
    session: AsyncSession,
    project: ProjectModel,
) -> str:
    lock = _PROJECTS_TO_RUN_NAMES_LOCK.setdefault(project.name, asyncio.Lock())
    run_name_base = generate_name()
    idx = 1
    async with lock:
        while (
            await get_run(
                session=session,
                project=project,
                run_name=f"{run_name_base}-{idx}",
            )
            is not None
        ):
            idx += 1
        return f"{run_name_base}-{idx}"
