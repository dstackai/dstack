from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dstack._internal.cli.models.endpoint_agent import AGENT_FINAL_REPORT_JSON_SCHEMA
from dstack._internal.cli.models.endpoint_presets import (
    EndpointBenchmark,
    EndpointBenchmarkLatency,
    EndpointBenchmarkMetrics,
    EndpointBenchmarkWorkload,
)
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.envs import EnvSentinel
from tests._internal.cli.endpoint_presets import (
    get_endpoint_benchmark,
    get_endpoint_preset,
)

pytestmark = pytest.mark.windows


class TestEndpointBenchmark:
    def test_agent_schema_matches_benchmark_model(self):
        schema = AGENT_FINAL_REPORT_JSON_SCHEMA["properties"]["benchmark"]
        assert set(schema["properties"]) == set(EndpointBenchmark.__fields__) - {
            "target",
            "client",
        }
        assert set(schema["required"]) == set(schema["properties"])
        workload_schema = schema["properties"]["workload"]
        metrics_schema = schema["properties"]["metrics"]
        assert set(workload_schema["properties"]) == set(EndpointBenchmarkWorkload.__fields__)
        assert set(workload_schema["required"]) == set(workload_schema["properties"])
        assert set(metrics_schema["properties"]) == set(EndpointBenchmarkMetrics.__fields__)
        assert set(metrics_schema["required"]) == set(metrics_schema["properties"])
        assert set(metrics_schema["properties"]["ttft_ms"]["properties"]) == set(
            EndpointBenchmarkLatency.__fields__
        )

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("failed_requests", 1, "must not include failed requests"),
            ("successful_requests", 15, "must match workload.num_requests"),
        ],
    )
    def test_rejects_inconsistent_successful_metrics(self, field, value, error):
        data = get_endpoint_benchmark().dict()
        data["metrics"][field] = value
        with pytest.raises(ValidationError, match=error):
            EndpointBenchmark.parse_obj(data)

    def test_rejects_tool_specific_metrics(self):
        data = get_endpoint_benchmark().dict()
        data["metrics"]["tool_specific"] = 1

        with pytest.raises(ValidationError, match="extra fields not permitted"):
            EndpointBenchmark.parse_obj(data)


class TestEndpointPresetStore:
    def test_saves_and_lists_self_contained_preset(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        preset = get_endpoint_preset()

        path = store.save(preset)

        assert path == (tmp_path / "presets" / "models--Qwen--Qwen3.5-27B" / "8f3a12c4.yaml")
        data = yaml.safe_load(path.read_text())
        assert data["base"] == preset.base
        assert data["id"] == preset.id
        assert data["model"] == preset.model
        assert data["created_at"] == preset.created_at.isoformat()
        assert "presets" not in data
        assert store.list() == [preset]
        assert store.get(preset.id) == preset
        assert not list(path.parent.glob("*.tmp"))

    def test_replaces_same_preset_id_atomically(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        preset = get_endpoint_preset()
        store.save(preset)

        updated = preset.copy(update={"context_length": 16384})
        store.save(updated)

        assert store.get(updated.id) == updated

    def test_rejects_duplicate_preset_id(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        preset = get_endpoint_preset()
        store.save(preset)
        store.save(preset.copy(update={"base": "Qwen/Another-Model"}))

        with pytest.raises(CLIError, match="is not unique"):
            store.get(preset.id)

    def test_rejects_preset_without_successful_benchmark(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        path = store.save(get_endpoint_preset())
        data = yaml.safe_load(path.read_text())
        data["validations"][0].pop("benchmark")
        path.write_text(yaml.safe_dump(data, sort_keys=False))

        with pytest.raises(CLIError, match="benchmark"):
            store.list()

    def test_preserves_literal_env_values(self, tmp_path: Path):
        store = EndpointPresetStore(tmp_path / "presets")
        preset = get_endpoint_preset()
        preset.service.env.update(
            {
                "TOKENIZERS_PARALLELISM": "false",
                "MODEL_LABEL": "monkey",
                "HF_TOKEN": EnvSentinel(key="HF_TOKEN"),
            }
        )

        path = store.save(preset)
        env = yaml.safe_load(path.read_text())["service"]["env"]

        assert "TOKENIZERS_PARALLELISM=false" in env
        assert "MODEL_LABEL=monkey" in env
        assert "HF_TOKEN" in env
