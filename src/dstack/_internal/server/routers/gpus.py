from typing import Annotated, Optional, Tuple

from fastapi import APIRouter, Depends
from packaging.version import Version

from dstack._internal.server.compatibility.gpus import patch_list_gpus_response
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.gpus import ListGpusRequest, ListGpusResponse
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services.gpus import list_gpus_grouped
from dstack._internal.server.utils.routers import (
    get_base_api_additional_responses,
    get_client_version,
)

project_router = APIRouter(
    prefix="/api/project/{project_name}/gpus",
    tags=["gpus"],
    responses=get_base_api_additional_responses(),
)


@project_router.post("/list", response_model=ListGpusResponse, response_model_exclude_none=True)
async def list_gpus(
    body: ListGpusRequest,
    client_version: Annotated[Optional[Version], Depends(get_client_version)],
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> ListGpusResponse:
    _, project = user_project
    resp = await list_gpus_grouped(project=project, run_spec=body.run_spec, group_by=body.group_by)
    patch_list_gpus_response(resp, client_version)
    return resp
