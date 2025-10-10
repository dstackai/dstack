from typing import Tuple

from fastapi import APIRouter, Depends

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import logs
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/project/{project_name}/logs",
    tags=["logs"],
    responses=get_base_api_additional_responses(),
)


@router.post(
    "/poll",
    response_model=JobSubmissionLogs,
)
async def poll_logs(
    body: PollLogsRequest,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
):
    _, project = user_project
    # The runner guarantees logs have different timestamps if throughput < 1k logs / sec.
    # Otherwise, some logs with duplicated timestamps may be filtered out.
    # This limitation is imposed by cloud log services that support up to millisecond timestamp resolution.
    return CustomORJSONResponse(await logs.poll_logs_async(project=project, request=body))
