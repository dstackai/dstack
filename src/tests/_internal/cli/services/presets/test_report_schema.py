import pytest

from dstack._internal.cli.models.preset_agent import PresetAgentFailure, PresetAgentSuccess
from dstack._internal.cli.services.presets.report_schema import (
    get_report_json_schema,
    get_strict_report_json_schema,
)
from dstack._internal.cli.services.presets.verify import _AGENT_RESULT_ADAPTER
from dstack._internal.core.models.configurations import ServiceConfiguration

pytestmark = pytest.mark.windows

# Every report key with no value, as the strict schema makes codex write them.
_NO_VALUES = {
    "run_id": None,
    "run_name": None,
    "service_yaml": None,
    "trial": None,
    "base": None,
    "model": None,
    "context_length": None,
    "benchmark": None,
    "failure_summary": None,
}
# Keywords the OpenAI strict structured-output mode rejects.
_FORBIDDEN = {
    "title",
    "default",
    "examples",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


class TestGetStrictReportJsonSchema:
    def test_every_object_requires_all_of_its_properties(self):
        objects = [
            node
            for node in _walk(get_strict_report_json_schema())
            if node.get("type") == "object" and "properties" in node
        ]

        assert objects
        for node in objects:
            assert node["required"] == list(node["properties"])
            assert node["additionalProperties"] is False

    def test_drops_the_keywords_strict_mode_rejects(self):
        for node in _walk(get_strict_report_json_schema()):
            assert not (set(node) & _FORBIDDEN), node
            if "$ref" in node:
                assert set(node) == {"$ref"}

    def test_keeps_the_agent_facing_shape(self):
        strict = get_strict_report_json_schema()

        assert set(strict["properties"]) == set(get_report_json_schema()["properties"])
        # The service stays a YAML string; an optional field is nullable; a field
        # with a default stays non-null so the model writes the default.
        assert strict["properties"]["service_yaml"] == {"type": ["string", "null"]}
        workload = strict["$defs"]["PresetWorkload"]["properties"]
        assert workload["dataset"]["anyOf"][-1] == {"type": "null"}
        assert workload["shared_prefix_tokens"]["type"] == "integer"

    @pytest.mark.parametrize(
        "data, expected",
        [
            (
                {
                    **_NO_VALUES,
                    "success": False,
                    "failure_summary": "codex smoke test: no trials were run",
                },
                PresetAgentFailure,
            ),
            (
                {
                    **_NO_VALUES,
                    "success": True,
                    "run_id": "2b0e3b0c-6c1e-4b7e-9c3a-1f2a3b4c5d6e",
                    "run_name": "qwen-preset-1",
                    "service_yaml": (
                        "type: service\nname: qwen-preset-1\nimage: vllm/vllm-openai:latest\n"
                        "commands:\n  - vllm serve Qwen/Qwen2.5-0.5B-Instruct\nport: 8000\n"
                        "model: Qwen/Qwen2.5-0.5B-Instruct\n"
                    ),
                    "trial": 1,
                    "base": "Qwen/Qwen2.5-0.5B-Instruct",
                    "model": "Qwen/Qwen2.5-0.5B-Instruct",
                    "context_length": 2048,
                    "benchmark": {
                        "tool": "vllm.bench serve",
                        "tool_version": "0.27.0",
                        "command": "vllm bench serve --model Qwen/Qwen2.5-0.5B-Instruct",
                        "workload": {
                            "api": "chat_completions",
                            "dataset": None,
                            "num_requests": 32,
                            "input_tokens": 128,
                            "output_tokens": 64,
                            "concurrency": 1,
                            "shared_prefix_tokens": 0,
                        },
                        "metrics": {
                            "successful_requests": 32,
                            "failed_requests": 0,
                            "duration_seconds": 40.5,
                            "total_input_tokens": 4096,
                            "total_output_tokens": 2048,
                            "output_tok_per_s": 50.6,
                            "per_user_tok_per_s": 50.6,
                            "ttft_ms": {"mean": 210.0, "p50": 200.0, "p99": 300.0},
                            "tpot_ms": {"mean": 19.8, "p50": 19.5, "p99": 25.0},
                        },
                    },
                },
                PresetAgentSuccess,
            ),
        ],
    )
    def test_reports_codex_produced_against_the_schema_parse(self, data, expected):
        # The shape `codex exec --output-schema` writes: every key present, the
        # ones the agent had no value for as `null`.
        assert set(data) == set(get_strict_report_json_schema()["properties"])

        report = _AGENT_RESULT_ADAPTER.validate_python(data, context={"redacted_values": []})

        assert isinstance(report, expected)
        if isinstance(report, PresetAgentSuccess):
            assert isinstance(report.service_yaml, ServiceConfiguration)
            assert report.benchmark.workload.dataset is None
            assert report.benchmark.workload.shared_prefix_tokens == 0
