import pytest

from dstack._internal.cli.models.endpoint_trials import EndpointPresetTrial

pytestmark = pytest.mark.windows


def get_trial_record(benchmark=True) -> dict:
    record = {
        "task": {
            "type": "task",
            "name": "qwen-endpoint-1",
            "image": "vllm/vllm-openai:v0.11.0",
            "commands": [
                "vllm serve Qwen/Qwen3-32B-AWQ --reasoning-parser qwen3 --port 8000",
            ],
        },
        "resources": {
            "cpu": "16",
            "memory": "93GB",
            "disk": "100GB",
            "gpu": {"name": "RTX5090", "memory": "32GB", "count": 1},
        },
        "benchmark": None,
    }
    if benchmark:
        record["benchmark"] = {
            "tool": "vllm bench serve",
            "tool_version": "0.11.0",
            "command": "vllm bench serve --model Qwen/Qwen3-32B-AWQ --num-prompts 64",
            "workload": {
                "api": "chat_completions",
                "num_requests": 64,
                "input_tokens": 1024,
                "output_tokens": 512,
                "concurrency": 8,
            },
            "metrics": {
                "successful_requests": 64,
                "failed_requests": 0,
                "duration_seconds": 78.1,
                "total_input_tokens": 65536,
                "total_output_tokens": 32768,
                "ttft_ms": {"mean": 1660.0, "p50": 1571.0, "p99": 2010.0},
                "tpot_ms": {"mean": 17.57, "p50": 17.5, "p99": 18.1},
            },
        }
    return record


class TestEndpointPresetTrial:
    def test_parses_measured_trial(self):
        trial = EndpointPresetTrial.parse_obj(get_trial_record())

        assert trial.task.name == "qwen-endpoint-1"
        assert trial.task.commands[0].startswith("vllm serve")
        assert trial.benchmark is not None
        assert trial.benchmark.workload.concurrency == 8
        assert trial.benchmark.metrics.tpot_ms.mean == 17.57

    def test_failed_trial_allows_null_benchmark(self):
        trial = EndpointPresetTrial.parse_obj(get_trial_record(benchmark=False))

        assert trial.benchmark is None
