import uuid
from datetime import timezone
from typing import List

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.common
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobStatus,
    JobSubmission,
    Run,
    RunSpec,
)
from dstack._internal.server.models import JobModel, ProjectModel, RunModel, UserModel
from dstack._internal.server.services import repos
from dstack._internal.server.services.jobs import get_jobs_from_run_spec


async def list_runs(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
) -> List[Run]:
    pass


async def get_run(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
):
    pass


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
    run_model = RunModel(
        id=uuid.uuid4(),
        project=project,
        repo=repo,
        user=user,
        run_name=run_spec.run_name,
        submitted_at=dstack._internal.utils.common.get_current_datetime(),
        status=JobStatus.SUBMITTED,
        run_spec=run_spec.json(),
    )
    session.add(run_model)
    jobs = get_jobs_from_run_spec(run_spec)
    for job in jobs:
        job_model = JobModel(
            id=uuid.uuid4(),
            run_id=run_model.id,
            run_name=run_spec.run_name,
            job_num=job.job_spec.job_num,
            job_name=job.job_spec.job_name,
            submission_num=0,
            submitted_at=run_model.submitted_at,
            status=JobStatus.SUBMITTED,
            job_spec_data=job.job_spec.json(),
            job_provisioning_data=None,
        )
        session.add(job_model)
    await session.commit()
    await session.refresh(run_model)
    run = run_model_to_run(run_model)
    return run


def run_model_to_run(run_model: RunModel) -> Run:
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    jobs = get_jobs_from_run_spec(run_spec)
    for job_model in run_model.jobs:
        job = jobs[job_model.job_num]
        job_provisioning_data = None
        if job_model.job_provisioning_data is not None:
            job_provisioning_data = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
        job_submission = JobSubmission(
            id=job_model.id,
            submission_num=job_model.submission_num,
            submitted_at=job_model.submitted_at.replace(tzinfo=timezone.utc),
            status=job_model.status,
            job_provisioning_data=job_provisioning_data,
        )
        job.job_submissions.append(job_submission)
    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        submitted_at=run_model.submitted_at.replace(tzinfo=timezone.utc),
        run_spec=run_spec,
        jobs=jobs,
    )
    return run
