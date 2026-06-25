import os
from dataclasses import dataclass
from typing import Optional

import requests

from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError

REQUEST_TIMEOUT_SECS = 120
DEFAULT_MAX_TOKENS = 4096

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

DEFAULTS = {
    PROVIDER_ANTHROPIC: {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-6",
    },
    PROVIDER_OPENAI: {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}
ANTHROPIC_VERSION = "2023-06-01"


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class HarnessLLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self.api_key = api_key or os.getenv("DSTACK_HARNESS_API_KEY")
        if not self.api_key:
            raise CLIError(
                "DSTACK_HARNESS_API_KEY is not set."
                " Export it before running [code]dstack endpoint create[/]."
            )
        self.provider = (
            provider or os.getenv("DSTACK_HARNESS_PROVIDER") or PROVIDER_ANTHROPIC
        ).lower()
        if self.provider not in DEFAULTS:
            raise CLIError(
                f"Unsupported harness provider [code]{self.provider}[/]."
                f" Supported: {', '.join(DEFAULTS)}."
            )
        defaults = DEFAULTS[self.provider]
        self.base_url = (
            base_url or os.getenv("DSTACK_HARNESS_BASE_URL") or defaults["base_url"]
        ).rstrip("/")
        self.model = model or os.getenv("DSTACK_HARNESS_MODEL") or defaults["model"]
        self.max_tokens = max_tokens

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider == PROVIDER_ANTHROPIC:
            return self._chat_anthropic(system_prompt, user_prompt)
        return self._chat_openai(system_prompt, user_prompt)

    def _chat_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/messages"
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        data = self._post(url, payload, headers)
        self._print_usage(_parse_anthropic_usage(data))
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise CLIError(f"Unexpected harness LLM response: {data}") from e

    def _chat_openai(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = self._post(url, payload, headers)
        self._print_usage(_parse_openai_usage(data))
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise CLIError(f"Unexpected harness LLM response: {data}") from e

    def _print_usage(self, usage: Optional[LLMUsage]) -> None:
        provider_label = self.provider.capitalize()
        console.print(f"[code]\\[harness][/] LLM Provider: {provider_label}")
        console.print(f"[code]\\[harness][/] LLM Model: {self.model}")
        if usage is None:
            return
        console.print(
            "[code]\\[harness][/] LLM tokens:"
            f" input={usage.input_tokens},"
            f" output={usage.output_tokens},"
            f" total={usage.total_tokens}"
        )

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECS,
            )
        except requests.RequestException as e:
            raise CLIError(f"Failed to call harness LLM: {e}") from e

        if response.status_code >= 400:
            raise CLIError(
                f"Harness LLM request failed with status {response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as e:
            raise CLIError(f"Unexpected harness LLM response: {response.text}") from e


def _parse_anthropic_usage(data: dict) -> Optional[LLMUsage]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return LLMUsage(
            input_tokens=int(usage["input_tokens"]),
            output_tokens=int(usage["output_tokens"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _parse_openai_usage(data: dict) -> Optional[LLMUsage]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return LLMUsage(
            input_tokens=int(usage["prompt_tokens"]),
            output_tokens=int(usage["completion_tokens"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
