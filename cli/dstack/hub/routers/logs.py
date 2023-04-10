from functools import partial
from typing import Any, AsyncIterable, Callable, Coroutine, List, Mapping, Optional, Union

import anyio
from fastapi import APIRouter, Depends
from starlette.background import BackgroundTask
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import Response
from starlette.types import Receive
from starlette.types import Scope as StarletteScope
from starlette.types import Send

from dstack.hub.models import PollLogs
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import get_project
from dstack.hub.security.permissions import ProjectMember

router = APIRouter(prefix="/api/project", tags=["logs"], dependencies=[Depends(ProjectMember())])


class JSONStreamingResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Optional[Mapping[str, str]] = None,
        media_type: Optional[str] = None,
        background: Optional[BackgroundTask] = None,
    ) -> None:
        if isinstance(content, AsyncIterable):
            self.body_iterator = content
        else:
            self.body_iterator = iterate_in_threadpool(content)
        self.status_code = status_code
        self.media_type = self.media_type if media_type is None else media_type
        self.background = background
        self.init_headers(headers)

    async def listen_for_disconnect(self, receive: Receive) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break

    async def stream_response(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        async for chunk in self.body_iterator:
            if not isinstance(chunk, bytes):
                chunk = chunk.json().encode(self.charset)
            await send({"type": "http.response.body", "body": chunk, "more_body": True})

        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def __call__(self, scope: StarletteScope, receive: Receive, send: Send) -> None:
        async with anyio.create_task_group() as task_group:

            async def wrap(func: Callable[[], Coroutine]) -> None:
                await func()
                task_group.cancel_scope.cancel()

            task_group.start_soon(wrap, partial(self.stream_response, send))
            await wrap(partial(self.listen_for_disconnect, receive))

        if self.background is not None:
            await self.background()


@router.post(
    "/{project_name}/logs/poll",
    response_class=JSONStreamingResponse,
)
async def poll_logs(project_name: str, body: PollLogs):
    project = await get_project(project_name=project_name)
    backend = get_backend(project)
    return JSONStreamingResponse(
        content=backend.poll_logs(
            repo_address=body.repo_address,
            job_heads=body.job_heads,
            start_time=body.start_time,
            attached=body.attached,
        ),
    )
