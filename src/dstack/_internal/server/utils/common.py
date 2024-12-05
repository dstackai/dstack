import asyncio
from typing import (
    Awaitable,
    Callable,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
)

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
