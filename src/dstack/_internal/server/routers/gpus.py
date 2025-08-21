from typing import Tuple

from fastapi import APIRouter, Depends

from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.gpus import ListGpusRequest, ListGpusResponse
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services.gpus import list_gpus_grouped
from dstack._internal.server.utils.routers import get_base_api_additional_responses

project_router = APIRouter(
    prefix="/api/project/{project_name}/gpus",
    tags=["gpus"],
    responses=get_base_api_additional_responses(),
)


@project_router.post("/list", response_model=ListGpusResponse, response_model_exclude_none=True)
async def list_gpus(
    body: ListGpusRequest,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> ListGpusResponse:
    _, project = user_project
    return await list_gpus_grouped(project=project, run_spec=body.run_spec, group_by=body.group_by)
