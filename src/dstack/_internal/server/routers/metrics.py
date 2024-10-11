from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import metrics

router = APIRouter(
    prefix="/api/project/{project_name}/metrics",
    tags=["metrics"],
)


@router.get(
    "/job/{run_name}",
)
async def get_job_metrics(
    run_name: str,
    replica_num: int = 0,
    job_num: int = 0,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> JobMetrics:
    _, project = user_project
    return await metrics.get_job_metrics(
        session=session,
        project=project,
        run_name=run_name,
        replica_num=replica_num,
        job_num=job_num,
    )
