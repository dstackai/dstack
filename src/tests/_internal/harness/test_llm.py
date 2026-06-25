from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.core.errors import CLIError
from dstack._internal.harness.llm import HarnessLLMClient


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = str(json_body)
    return response


class TestHarnessLLMClient:
    def test_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("DSTACK_HARNESS_API_KEY", raising=False)
        with pytest.raises(CLIError):
            HarnessLLMClient()

    def test_anthropic_request_shape(self, monkeypatch):
        monkeypatch.delenv("DSTACK_HARNESS_PROVIDER", raising=False)
        monkeypatch.delenv("DSTACK_HARNESS_BASE_URL", raising=False)
        monkeypatch.delenv("DSTACK_HARNESS_MODEL", raising=False)
        client = HarnessLLMClient(api_key="test-key")
        assert client.provider == "anthropic"

        with patch("dstack._internal.harness.llm.requests.post") as post:
            post.return_value = _mock_response(
                200,
                {
                    "content": [{"type": "text", "text": "yaml here"}],
                    "usage": {"input_tokens": 10, "output_tokens": 24},
                },
            )
            result = client.chat("system", "user")

        assert result == "yaml here"
        called_url = post.call_args.args[0]
        called_kwargs = post.call_args.kwargs
        assert called_url.endswith("/messages")
        assert called_kwargs["headers"]["x-api-key"] == "test-key"
        assert called_kwargs["headers"]["anthropic-version"] == "2023-06-01"
        assert called_kwargs["json"]["system"] == "system"
        assert called_kwargs["json"]["max_tokens"] > 0
        assert called_kwargs["json"]["messages"] == [{"role": "user", "content": "user"}]

    def test_openai_request_shape(self):
        client = HarnessLLMClient(api_key="test-key", provider="openai")

        with patch("dstack._internal.harness.llm.requests.post") as post:
            post.return_value = _mock_response(
                200,
                {
                    "choices": [{"message": {"content": "yaml here"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                },
            )
            result = client.chat("system", "user")

        assert result == "yaml here"
        called_url = post.call_args.args[0]
        called_kwargs = post.call_args.kwargs
        assert called_url.endswith("/chat/completions")
        assert called_kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_raises_on_error_status(self):
        client = HarnessLLMClient(api_key="test-key", provider="anthropic")
        with patch("dstack._internal.harness.llm.requests.post") as post:
            post.return_value = _mock_response(401, {"error": "unauthorized"})
            with pytest.raises(CLIError):
                client.chat("system", "user")

    def test_prints_token_usage_for_anthropic(self, capsys):
        client = HarnessLLMClient(api_key="test-key", provider="anthropic")
        with patch("dstack._internal.harness.llm.requests.post") as post:
            post.return_value = _mock_response(
                200,
                {
                    "content": [{"type": "text", "text": "yaml here"}],
                    "usage": {"input_tokens": 10, "output_tokens": 24},
                },
            )
            client.chat("system", "user")

        output = capsys.readouterr().out
        assert "LLM Provider: Anthropic" in output
        assert "LLM Model:" in output
        assert "input=10" in output
        assert "output=24" in output
        assert "total=34" in output
