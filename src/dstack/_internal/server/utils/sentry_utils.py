import asyncio
import functools
from typing import Optional

import sentry_sdk
from sentry_sdk.types import Event, Hint, SamplingContext

from dstack._internal.server import settings

SCHEDULED_TASKS_PREFIX = "scheduled_tasks"
PIPELINE_TASKS_PREFIX = "pipeline_tasks"


def instrument_scheduled_task(f):
    return instrument_named_task(f"{SCHEDULED_TASKS_PREFIX}.{f.__name__}")


def instrument_pipeline_task(name: str):
    return instrument_named_task(f"{PIPELINE_TASKS_PREFIX}.{name}")


def instrument_named_task(name: str):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            with sentry_sdk.isolation_scope():
                with sentry_sdk.start_transaction(name=name):
                    return await f(*args, **kwargs)

        return wrapper

    return decorator


def sentry_traces_sampler(sampling_context: SamplingContext) -> float:
    parent_sampling_decision = sampling_context["parent_sampled"]
    if parent_sampling_decision is not None:
        return float(parent_sampling_decision)
    transaction_context = sampling_context["transaction_context"]
    name = transaction_context.get("name")
    if name is not None:
        if _is_background_transaction(name):
            return settings.SENTRY_TRACES_BACKGROUND_SAMPLE_RATE
    return settings.SENTRY_TRACES_SAMPLE_RATE


class AsyncioCancelledErrorFilterEventProcessor:
    # See https://docs.sentry.io/platforms/python/configuration/filtering/#filtering-error-events
    def __call__(self, event: Event, hint: Hint) -> Optional[Event]:
        exc_info = hint.get("exc_info")
        if exc_info and isinstance(exc_info[1], asyncio.CancelledError):
            return None
        return event


def _is_background_transaction(name: str) -> bool:
    return name.startswith(SCHEDULED_TASKS_PREFIX) or name.startswith(PIPELINE_TASKS_PREFIX)
