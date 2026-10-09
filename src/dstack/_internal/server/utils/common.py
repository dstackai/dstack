import asyncio
import inspect
from typing import (
    Awaitable,
    Callable,
    Iterable,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)

ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


@overload
async def gather_map_async(
    items: Sequence[ItemT],
    func: Callable[[ItemT], Awaitable[ResultT]],
    *,
    return_exceptions: Literal[False] = False,
    max_concurrency: Optional[int] = None,
) -> List[Tuple[ItemT, ResultT]]: ...


@overload
async def gather_map_async(
    items: Sequence[ItemT],
    func: Callable[[ItemT], Awaitable[ResultT]],
    *,
    return_exceptions: bool,
    max_concurrency: Optional[int] = None,
) -> List[Tuple[ItemT, Union[ResultT, BaseException]]]: ...


async def gather_map_async(
    items: Sequence[ItemT],
    func: Callable[[ItemT], Awaitable[ResultT]],
    *,
    return_exceptions: bool = False,
    max_concurrency: Optional[int] = None,
) -> Union[List[Tuple[ItemT, ResultT]], List[Tuple[ItemT, Union[ResultT, BaseException]]]]:
    """
    A parallel wrapper around asyncio.gather that returns a list of tuples (item, result).
    Args:
        items: list of items to be processed
        func: function to be applied to each item, return awaitable coroutine
        return_exceptions: passed to gather_async
        max_concurrency: passed to gather_async

    Returns:
        list of tuples (item, result) or (item, exception) if return_exceptions is True
    """
    results = await gather_async(
        [func(item) for item in items],
        return_exceptions=return_exceptions,
        max_concurrency=max_concurrency,
    )
    return list(zip(items, results))


@overload
async def gather_async(
    aws: Sequence[Awaitable[ResultT]],
    *,
    return_exceptions: Literal[False] = False,
    max_concurrency: Optional[int] = None,
) -> List[ResultT]: ...


@overload
async def gather_async(
    aws: Sequence[Awaitable[ResultT]],
    *,
    return_exceptions: bool,
    max_concurrency: Optional[int] = None,
) -> List[Union[ResultT, BaseException]]: ...


async def gather_async(
    aws: Sequence[Awaitable[ResultT]],
    *,
    return_exceptions: bool = False,
    max_concurrency: Optional[int] = None,
) -> Union[List[ResultT], List[Union[ResultT, BaseException]]]:
    """
    Like asyncio.gather, but takes a sequence of awaitables and also:
    - Runs at most `max_concurrency` awaitables at once, unlimited if None. Only awaitables that
      start when awaited, such as coroutines, can be limited. Tasks and futures already run.
    - Cancels the remaining awaitables when one fails and `return_exceptions` is False.
    """
    tasks: List[asyncio.Future[ResultT]] = []
    try:
        semaphore = None
        if max_concurrency is not None:
            if max_concurrency < 1:
                raise ValueError("max_concurrency must be >= 1")
            semaphore = asyncio.BoundedSemaphore(max_concurrency)
        for aw in aws:
            if semaphore is not None:
                aw = _await_with_semaphore(aw, semaphore)
            tasks.append(asyncio.ensure_future(aw))
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    finally:
        # asyncio.gather doesn't cancel the remaining tasks when one of them fails
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        # Coroutines that never started (queued when cancelled, or rejected by validation)
        # would warn that they were never awaited
        for aw in aws:
            if inspect.iscoroutine(aw):
                aw.close()


def join_byte_stream_checked(stream: Iterable[bytes], max_size: int) -> Optional[bytes]:
    """
    Join an iterable of `bytes` values into one `bytes` value,
    unless its size exceeds `max_size`.
    """
    result = b""
    for chunk in stream:
        if len(result) + len(chunk) > max_size:
            return None
        result += chunk
    return result


SCHEDULED_TASKS_PREFIX = "scheduled_tasks"
PIPELINE_TASKS_PREFIX = "pipeline_tasks"


def is_background_task_name(name: str) -> bool:
    return name.startswith(SCHEDULED_TASKS_PREFIX) or name.startswith(PIPELINE_TASKS_PREFIX)


async def _await_with_semaphore(aw: Awaitable[ResultT], semaphore: asyncio.Semaphore) -> ResultT:
    async with semaphore:
        return await aw
