import asyncio
import functools
from typing import Callable, ParamSpec, TypeVar

R = TypeVar("R")
P = ParamSpec("P")


async def run_async(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    func_with_args = functools.partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, func_with_args)
