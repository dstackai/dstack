from typing import Any

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsUsage,
    PromptTokensDetails,
)
from dstack._internal.proxy.lib.schemas.usage import TokenUsage
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE, UsageAttempt, normalize_usage
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter", "function_call"}


class StreamUsage:
    def __init__(self, attempt: UsageAttempt, n: int):
        self._attempt = attempt
        self._n = n
        self._per_choice = attempt.profile == "vllm-0.19.1-per-choice"
        self.request_progress = attempt.profile != VLLM_PROFILE
        self._final = False
        self._finished_choices: set[int] = set()
        self._finish_usage: dict[int, TokenUsage] = {}
        self._outputs: dict[int, int] = {}
        self._completion = 0
        self._prompt = 0
        self._confirmed_input: tuple[int, int] | None = None
        self._invalid_progress = False
        self._terminal: ChatCompletionsChunk | None = None

    def observe(self, chunk: ChatCompletionsChunk, raw_usage: Any) -> ChatCompletionsChunk | None:
        if self._final:
            return None
        usage = normalize_usage(raw_usage, self._attempt.profile)
        if not chunk.choices:
            if usage is None:
                return None
            self._confirm(usage, raw_usage)
            public_usage = validate_extra_ignore(ChatCompletionsUsage, raw_usage)
            return chunk.model_copy(update={"usage": public_usage})
        if self.request_progress and not self._invalid_progress:
            self._observe_progress(chunk, usage, raw_usage)
        return None

    def complete(self) -> ChatCompletionsChunk | None:
        if self._final or self._terminal is None or self._invalid_progress:
            return None
        self._attempt.observe_usage(self._terminal.usage)
        return self._terminal

    def _confirm(self, usage: TokenUsage, raw_usage: Any) -> None:
        cached = (
            self._confirmed_input[1]
            if self._confirmed_input is not None and self._confirmed_input[0] == self._prompt
            else None
        )
        if self._outputs and (
            usage.completion_tokens != self._completion
            or usage.prompt_tokens != self._prompt
            or (cached is not None and usage.cached_prompt_tokens != cached)
        ):
            logger.debug(
                "Upstream final usage differs from streaming progress: "
                "prompt %d -> %d, cached %s -> %d, completion %d -> %d",
                self._prompt,
                usage.prompt_tokens,
                cached,
                usage.cached_prompt_tokens,
                self._completion,
                usage.completion_tokens,
            )
        self._attempt.observe_usage(raw_usage)
        self._final = True

    def _observe_progress(
        self, chunk: ChatCompletionsChunk, usage: TokenUsage | None, raw_usage: Any
    ) -> None:
        indices = {choice.index for choice in chunk.choices}
        finishes = {
            choice.index for choice in chunk.choices if choice.finish_reason in _FINISH_REASONS
        }
        if (
            any(index < 0 or index >= self._n for index in indices)
            or len(indices) != len(chunk.choices)
            or (indices - finishes) & self._finished_choices
            or (self._per_choice and usage is not None and len(indices) != 1)
        ):
            self._invalid_progress = True
            return

        new_finishes = finishes - self._finished_choices
        self._finished_choices.update(finishes)
        if usage is None:
            return
        if indices == finishes and finishes <= self._finish_usage.keys():
            # A delayed replay may precede the latest request-wide count.
            if any(self._finish_usage[index] != usage for index in finishes):
                self._invalid_progress = True
            return

        key = next(iter(indices)) if self._per_choice else 0
        previous = self._outputs.get(key, 0)
        has_cache = raw_usage.get("prompt_tokens_details") is not None
        if (
            usage.completion_tokens < previous
            or usage.prompt_tokens < self._prompt
            or (
                has_cache
                and self._confirmed_input is not None
                and usage.cached_prompt_tokens < self._confirmed_input[1]
            )
            or self._terminal is not None
        ):
            self._invalid_progress = True
            return

        self._outputs[key] = usage.completion_tokens
        self._completion += usage.completion_tokens - previous
        self._prompt = usage.prompt_tokens
        if has_cache:
            self._confirmed_input = (usage.prompt_tokens, usage.cached_prompt_tokens)

        # Cache details can first arrive in the final event. Until observed,
        # charge only output on an incomplete request.
        prompt, cached = self._confirmed_input or (0, 0)
        self._attempt.observe_partial_usage(
            TokenUsage(
                prompt_tokens=prompt,
                cached_prompt_tokens=cached,
                completion_tokens=self._completion,
                total_tokens=prompt + self._completion,
            )
        )

        for index in finishes:
            self._finish_usage.setdefault(index, usage)
        if self._per_choice:
            complete = bool(finishes) and len(self._finish_usage) == self._n
        else:
            complete = bool(new_finishes) and len(self._finished_choices) == self._n
        # A snapshot must accompany the last finish. For per-choice counts,
        # every choice also needs its own terminal snapshot.
        if complete:
            public_usage = ChatCompletionsUsage(
                prompt_tokens=self._prompt,
                completion_tokens=self._completion,
                total_tokens=self._prompt + self._completion,
                prompt_tokens_details=(
                    PromptTokensDetails(cached_tokens=cached)
                    if self._confirmed_input is not None and prompt == self._prompt
                    else None
                ),
            )
            self._terminal = chunk.model_copy(update={"choices": [], "usage": public_usage})
