import itertools
from datetime import timedelta
from functools import partial
from typing import Any, AsyncIterable, Callable, Coroutine, List, Mapping, Optional

import anyio
from fastapi import APIRouter, Depends
from starlette.background import BackgroundTask
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import Response
from starlette.types import Receive
from starlette.types import Scope as StarletteScope
from starlette.types import Send

from dstack.core.log_event import LogEvent
from dstack.hub.models import PollLogs
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember
from dstack.utils.common import get_current_datetime

router = APIRouter(prefix="/api/project", tags=["logs"], dependencies=[Depends(ProjectMember())])


@router.post(
    "/{project_name}/logs/poll",
)
async def poll_logs(project_name: str, body: PollLogs) -> List[LogEvent]:
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    start_time = body.start_time
    if start_time is None:
        start_time = get_current_datetime() - timedelta(days=30)
    logs_generator = backend.poll_logs(
        repo_id=body.repo_id,
        run_name=body.run_name,
        start_time=start_time,
        end_time=body.end_time,
        descending=body.descending,
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
