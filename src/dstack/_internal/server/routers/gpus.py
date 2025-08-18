from typing import Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.gpus import GetRunGpusRequest, RunGpusResponse
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services.gpus import get_run_gpus_grouped
from dstack._internal.server.utils.routers import get_base_api_additional_responses

project_router = APIRouter(
    prefix="/api/project/{project_name}/gpus",
    tags=["gpus"],
    responses=get_base_api_additional_responses(),
)


@project_router.post("/list", response_model=RunGpusResponse, response_model_exclude_none=True)
async def get_run_gpus(
    body: GetRunGpusRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> RunGpusResponse:
    _, project = user_project
    return await get_run_gpus_grouped(
        session=session, project=project, run_spec=body.run_spec, group_by=body.group_by
    )
