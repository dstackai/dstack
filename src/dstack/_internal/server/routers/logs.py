from fastapi import APIRouter

from dstack._internal.core.models.logs import JobSubmissionLogs
from dstack._internal.server.schemas.logs import PollLogsRequest

router = APIRouter(
    prefix="/api/project/{project_name}/logs",
    tags=["logs"],
)


@router.post(
    "/poll",
)
async def poll_logs(project_name: str, body: PollLogsRequest) -> JobSubmissionLogs:
    pass
