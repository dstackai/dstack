from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.metrics import JobMetrics
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import metrics
from dstack._internal.server.services.jobs import get_run_job_model
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/project/{project_name}/metrics",
    tags=["metrics"],
    responses=get_base_api_additional_responses(),
)


@router.get(
    "/job/{run_name}",
    response_model=JobMetrics,
)
async def get_job_metrics(
    run_name: str,
    replica_num: int = 0,
    job_num: int = 0,
    limit: int = 1,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    """
    Returns job-level metrics such as hardware utilization
    given `run_name`, `replica_num`, and `job_num`.
    If only `run_name` is specified, returns metrics of `(replica_num=0, job_num=0)`.
    By default, returns one latest sample. To control time window/number of samples, use
    `limit`, `after`, `before`.

    Supported metrics (all optional):
    * `cpus_detected_num`
    * `cpu_usage_percent`
    * `memory_total_bytes`
    * `memory_usage_bytes`
    * `memory_working_set_bytes`
    * `gpus_detected_num`
    * `gpu_memory_total_bytes`
    * `gpu_memory_usage_bytes_gpu{i}`
    * `gpu_util_percent_gpu{i}`
    """
    _, project = user_project

    job_model = await get_run_job_model(
        session=session,
        project=project,
        run_name=run_name,
        replica_num=replica_num,
        job_num=job_num,
    )
    if job_model is None:
        raise ResourceNotExistsError("Found no job with given parameters")

    return CustomORJSONResponse(
        await metrics.get_job_metrics(
            session=session,
            job_model=job_model,
            limit=limit,
            after=after,
            before=before,
        )
    )
