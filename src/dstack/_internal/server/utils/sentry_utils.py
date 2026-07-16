import asyncio
from typing import Optional

from sentry_sdk.types import Event, Hint, SamplingContext

from dstack._internal.server import settings
from dstack._internal.server.utils.common import is_background_task_name


def sentry_traces_sampler(sampling_context: SamplingContext) -> float:
    parent_sampling_decision = sampling_context["parent_sampled"]
    if parent_sampling_decision is not None:
        return float(parent_sampling_decision)
    transaction_context = sampling_context["transaction_context"]
    name = transaction_context.get("name")
    if name is not None:
        if is_background_task_name(name):
            return settings.SENTRY_TRACES_BACKGROUND_SAMPLE_RATE
    return settings.SENTRY_TRACES_SAMPLE_RATE


class AsyncioCancelledErrorFilterEventProcessor:
    # See https://docs.sentry.io/platforms/python/configuration/filtering/#filtering-error-events
    def __call__(self, event: Event, hint: Hint) -> Optional[Event]:
        exc_info = hint.get("exc_info")
        if exc_info and isinstance(exc_info[1], asyncio.CancelledError):
            return None
        return event
