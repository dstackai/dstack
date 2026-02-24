import asyncio
import functools
from typing import Optional

import sentry_sdk
from sentry_sdk.types import Event, Hint


def instrument_scheduled_task(f):
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        with sentry_sdk.isolation_scope():
            with sentry_sdk.start_transaction(name=f"scheduled_tasks.{f.__name__}"):
                return await f(*args, **kwargs)

    return wrapper


def instrument_named_task(name: str):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            with sentry_sdk.isolation_scope():
                with sentry_sdk.start_transaction(name=name):
                    return await f(*args, **kwargs)

        return wrapper

    return decorator


class AsyncioCancelledErrorFilterEventProcessor:
    # See https://docs.sentry.io/platforms/python/configuration/filtering/#filtering-error-events
    def __call__(self, event: Event, hint: Hint) -> Optional[Event]:
        exc_info = hint.get("exc_info")
        if exc_info and isinstance(exc_info[1], asyncio.CancelledError):
            return None
        return event
