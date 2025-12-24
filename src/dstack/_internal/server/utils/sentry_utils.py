import asyncio
import functools
from typing import Optional

import sentry_sdk
from sentry_sdk.types import Event, Hint


def instrument_background_task(f):
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        with sentry_sdk.start_transaction(name=f"background.{f.__name__}"):
            return await f(*args, **kwargs)

    return wrapper


class AsyncioCancelledErrorFilterEventProcessor:
    # See https://docs.sentry.io/platforms/python/configuration/filtering/#filtering-error-events
    def __call__(self, event: Event, hint: Hint) -> Optional[Event]:
        exc_info = hint.get("exc_info")
        if exc_info and isinstance(exc_info[1], asyncio.CancelledError):
            return None
        return event
