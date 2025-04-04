import asyncio
import threading
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


class DaemonEventLoop:
    """
    A wrapper around asyncio.EventLoop that runs the loop in a daemon thread.
    The thread is started with the first `await_` call.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._start_lock = threading.Lock()
        self._started = False

    def await_(self, awaitable: Awaitable[T]) -> T:
        with self._start_lock:
            if not self._started:
                threading.Thread(target=self._loop.run_forever, daemon=True).start()
                self._started = True
        future = asyncio.run_coroutine_threadsafe(_coroutine(awaitable), self._loop)
        return future.result()


async def _coroutine(awaitable: Awaitable[T]) -> T:
    return await awaitable
