import asyncio
from functools import partial
from typing import (
    Awaitable,
    Callable,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
)

from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


async def run_async(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    func_with_args = partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, func_with_args)


ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


async def gather_map_async(
    items: Sequence[ItemT],
    func: Callable[[ItemT], Awaitable[ResultT]],
    *,
    return_exceptions: bool = False,
) -> List[Tuple[ItemT, Union[ResultT, BaseException]]]:
    """
    A parallel wrapper around asyncio.gather that returns a list of tuples (item, result).
    Args:
        items: list of items to be processed
        func: function to be applied to each item, return awaitable coroutine
        return_exceptions: passed to asyncio.gather

    Returns:
        list of tuples (item, result) or (item, exception) if return_exceptions is True
    """
    return [
        (item, result)
        for item, result in zip(
            items,
            await asyncio.gather(
                *(func(item) for item in items), return_exceptions=return_exceptions
            ),
        )
    ]


KeyT = TypeVar("KeyT")


async def wait_unlock(
    lock: asyncio.Lock, locked: Set[KeyT], keys: Iterable[KeyT], *, delay: float = 0.1
):
    """
    Wait until all keys are unlocked (not presented in the `locked` set).
    Lock is released during the sleep.
    """
    keys_set = set(keys)
    while True:
        async with lock:
            if not keys_set.intersection(locked):
                return
        await asyncio.sleep(delay)


async def wait_to_lock(lock: asyncio.Lock, locked: Set[KeyT], key: KeyT, *, delay: float = 0.1):
    """
    Retry locking until the key is locked.
    Lock is released during the sleep.
    """
    while True:
        async with lock:
            if key not in locked:
                locked.add(key)
                return
        await asyncio.sleep(delay)


async def wait_to_lock_many(
    lock: asyncio.Lock, locked: Set[KeyT], keys: List[KeyT], *, delay: float = 0.1
):
    """
    Retry locking until all the keys are locked.
    Lock is released during the sleep.
    The keys must be sorted to prevent deadlock.
    """
    left_to_lock = keys.copy()
    while len(left_to_lock) > 0:
        async with lock:
            for key in left_to_lock:
                if key not in locked:
                    locked.add(key)
                    left_to_lock.remove(key)
        await asyncio.sleep(delay)


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
