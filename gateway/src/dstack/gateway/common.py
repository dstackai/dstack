import asyncio
import contextlib
import functools
import json
from typing import Any, AsyncIterator, Callable, Dict, ParamSpec, TypeVar

import httpx
from pydantic import BaseModel

R = TypeVar("R")
P = ParamSpec("P")


async def run_async(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    func_with_args = functools.partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, func_with_args)


class AsyncClientWrapper(httpx.AsyncClient):
    def __del__(self):
        with contextlib.suppress(Exception):
            asyncio.get_running_loop().create_task(self.aclose())

    async def stream_sse(self, url: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        async with self.stream("POST", url, **kwargs) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    yield json.loads(line[len("data:") :].strip("\n"))


class OkResponse(BaseModel):
    status: str = "ok"
