"""Complete owned cleanup before propagating cancellation to the caller."""

import asyncio
from typing import TypeVar

import anyio

T = TypeVar("T")


async def await_completion(task: asyncio.Task[T]) -> T:
    cancelled: asyncio.CancelledError | None = None
    # AnyIO's level cancellation and repeated direct Task.cancel() both occur in HTTP shutdown.
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as exc:
                cancelled = exc
        result = task.result()
    if cancelled is not None:
        raise cancelled
    return result
