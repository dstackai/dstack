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
    """
    Returns job-level metrics such as hardware utilization
    given `run_name`, `replica_num`, and `job_num`.
    If only `run_name` is specified, returns metrics of `(replica_num=0, job_num=0)`.

    Supported metrics: [
        "cpu_usage_percent",
        "memory_usage_bytes",
        "memory_working_set_bytes",
        "gpus_detected_num",
        "gpu_memory_usage_bytes_gpu{i}",
        "gpu_util_percent_gpu{i}"
    ]
    """
    _, project = user_project
    return await metrics.get_job_metrics(
        session=session,
        project=project,
        run_name=run_name,
        replica_num=replica_num,
        job_num=job_num,
    )
