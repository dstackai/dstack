"""Usage observation is optional for shared proxy consumers."""

from collections.abc import Mapping
from typing import Any, Literal, get_args

from pydantic import BaseModel, ValidationError

from dstack._internal.proxy.lib.schemas.usage import TokenUsage, UsageKey

VLLM_PROFILE = "vllm-0.19.1-prompt-details"
MeteringProfile = Literal[
    "vllm-0.19.1-prompt-details",
    "vllm-0.19.1-per-choice",
    "dynamo-1.6.2-rust",
    "dynamo-1.6.2-vllm",
]
METERING_PROFILES = frozenset(get_args(MeteringProfile))
MAX_JSON_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_SSE_EVENT_BYTES = 1024 * 1024


def normalize_usage(usage: Any, profile: str) -> TokenUsage | None:
    if profile not in METERING_PROFILES:
        return None
    if isinstance(usage, BaseModel):
        usage = usage.model_dump()
    if not isinstance(usage, Mapping):
        return None
    details = usage.get("prompt_tokens_details")
    if details is None:
        cached = 0
    elif isinstance(details, Mapping):
        cached = details.get("cached_tokens")
    else:
        return None
    try:
        return TokenUsage.model_validate(
            {
                "prompt_tokens": usage.get("prompt_tokens"),
                "cached_prompt_tokens": cached,
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }
        )
    except ValidationError:
        return None


class UsageAttempt:
    """No-op default; Gateway supplies a concrete per-attempt observer."""

    profile: str = VLLM_PROFILE

    def observe_usage(self, usage: Any) -> None:
        pass

    def observe_partial_usage(self, usage: TokenUsage | None) -> None:
        pass

    def mark_dispatched(self) -> None:
        pass

    def mark_upstream_done(self) -> None:
        pass

    async def finish(self) -> None:
        pass


class UsageObserver:
    def profile_for(self, service_id: str | None) -> str | None:
        return None

    def start_attempt(self, key: UsageKey, profile: str) -> UsageAttempt:
        return UsageAttempt()
