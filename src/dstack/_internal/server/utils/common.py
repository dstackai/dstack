import asyncio
from functools import partial
from typing import Awaitable, Callable, List, Sequence, Tuple, TypeVar, Union

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
) -> List[Tuple[ItemT, Union[ResultT, Exception]]]:
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
