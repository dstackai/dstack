import functools

import sentry_sdk

from dstack._internal.server.utils import otel
from dstack._internal.server.utils.common import PIPELINE_TASKS_PREFIX, SCHEDULED_TASKS_PREFIX


def instrument_scheduled_task(f):
    return instrument_named_task(f"{SCHEDULED_TASKS_PREFIX}.{f.__name__}")(f)


def instrument_pipeline_task(name: str):
    return instrument_named_task(f"{PIPELINE_TASKS_PREFIX}.{name}")


def instrument_named_task(name: str):
    def decorator(f):
        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            with sentry_sdk.isolation_scope():
                with sentry_sdk.start_transaction(name=name):
                    with otel.task_span(name):
                        return await f(*args, **kwargs)

        return wrapper

    return decorator
