import uuid
from typing import List

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import Run, RunSpec
from dstack._internal.server.models import ProjectModel, RunModel, UserModel
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
        project_id=project.id,
        repo_id=repo.id,
        user_id=user.id,
        run_name=run_spec.run_name,
        run_spec=run_spec.json(),
    )
    session.add(run_model)
    await session.commit()
    run = run_model_to_run(run_model)
    return run


def run_model_to_run(run_model: RunModel) -> Run:
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    jobs = get_jobs_from_run_spec(run_spec)
    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        run_spec=run_spec,
        jobs=jobs,
    )
    return run
