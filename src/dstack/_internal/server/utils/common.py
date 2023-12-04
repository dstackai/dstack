import asyncio
from functools import partial
from typing import Callable, TypeVar

from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


async def run_async(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    func_with_args = partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, func_with_args)
