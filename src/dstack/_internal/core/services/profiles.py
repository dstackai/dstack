from typing import Optional, Tuple

from dstack._internal.core.models.profiles import (
    DEFAULT_RETRY_DURATION,
    Profile,
    RetryEvent,
    TerminationPolicy,
)
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


def get_termination(
    profile: Profile, default_termination_idle_time: int
) -> Tuple[TerminationPolicy, int]:
    termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
    termination_idle_time = default_termination_idle_time
    if profile.termination_policy is not None:
        termination_policy = profile.termination_policy
    if profile.termination_idle_time is not None:
        termination_idle_time = profile.termination_idle_time
    if profile.idle_duration is not None and int(profile.idle_duration) < 0:
        termination_policy = TerminationPolicy.DONT_DESTROY
    elif profile.idle_duration is not None:
        termination_idle_time = profile.idle_duration
    if termination_policy == TerminationPolicy.DONT_DESTROY:
        termination_idle_time = -1
    return termination_policy, int(termination_idle_time)
