from typing import Optional

from dstack._internal.core.models.profiles import DEFAULT_RETRY_DURATION, Profile, RetryEvent
from dstack._internal.core.models.runs import Retry


def get_retry(profile: Profile) -> Optional[Retry]:
    profile_retry = profile.retry
    if profile_retry is None:
        # Handle retry_policy before retry was introduced
        # TODO: Remove once retry_policy no longer supported
        profile_retry_policy = profile.retry_policy
        if profile_retry_policy is None:
            return None
        if not profile_retry_policy.retry:
            return None
        duration = profile_retry_policy.duration or DEFAULT_RETRY_DURATION
        return Retry(
            on_events=[RetryEvent.NO_CAPACITY, RetryEvent.INTERRUPTION, RetryEvent.ERROR],
            duration=duration,
        )
    if isinstance(profile_retry, bool):
        if profile_retry:
            return Retry(
                on_events=[RetryEvent.NO_CAPACITY, RetryEvent.INTERRUPTION, RetryEvent.ERROR],
                duration=DEFAULT_RETRY_DURATION,
            )
        return None
    profile_retry = profile_retry.copy()
    if profile_retry.duration is None:
        profile_retry.duration = DEFAULT_RETRY_DURATION
    return Retry.parse_obj(profile_retry)
