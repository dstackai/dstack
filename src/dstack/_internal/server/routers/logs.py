from typing import Tuple

from fastapi import APIRouter, Depends

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.security.permissions import ProjectMember
from dstack._internal.server.services import logs

router = APIRouter(
    prefix="/api/project/{project_name}/logs",
    tags=["logs"],
)


@router.post(
    "/poll",
)
async def poll_logs(
    body: PollLogsRequest,
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectMember()),
) -> JobSubmissionLogs:
    _, project = user_project
    return logs.poll_logs(project=project, request=body)
