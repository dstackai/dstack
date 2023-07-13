import itertools
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends

from dstack._internal.core.log_event import LogEvent
from dstack._internal.hub.models import PollLogs
from dstack._internal.hub.routers.util import get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime

router = APIRouter(prefix="/api/project", tags=["logs"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/logs/poll",
)
async def poll_logs(project_name: str, body: PollLogs) -> List[LogEvent]:
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    start_time = body.start_time
    if start_time is None:
        start_time = get_current_datetime() - timedelta(days=30)
    logs_generator = await run_async(
        backend.poll_logs,
        body.repo_id,
        body.run_name,
        start_time,
        body.end_time,
        body.descending,
        body.diagnose,
    )
    if body.prev_event_id is None:
        return list(itertools.islice(logs_generator, body.limit))
    # We'll fetch more than limit logs because we'll skip logs
    # before and including prev_event_id that have the same timestamp.
    # It should work if there are not that many logs with the same timestamp.
    fetch_limit = body.limit + 50
    logs = list(itertools.islice(logs_generator, fetch_limit))
    event_ids = [l.event_id for l in logs]
    try:
        prev_event_idx = event_ids.index(body.prev_event_id)
    except ValueError:
        return logs[: body.limit]
    return logs[prev_event_idx + 1 :][: body.limit]
