import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.preset_agent import AGENT_FINAL_REPORT_JSON_SCHEMA
from dstack._internal.cli.models.presets import (
    PresetBenchmark,
    PresetBenchmarkLatency,
    PresetBenchmarkMetrics,
    PresetBenchmarkWorkload,
)
from tests._internal.cli.preset_factories import get_preset_benchmark

pytestmark = pytest.mark.windows


class TestPresetBenchmark:
    def test_agent_schema_matches_benchmark_model(self):
        schema = AGENT_FINAL_REPORT_JSON_SCHEMA["properties"]["benchmark"]
        assert set(schema["properties"]) == set(PresetBenchmark.__fields__) - {
            "target",
            "client",
        }
        assert set(schema["required"]) == set(schema["properties"])
        workload_schema = schema["properties"]["workload"]
        metrics_schema = schema["properties"]["metrics"]
        assert set(workload_schema["properties"]) == set(PresetBenchmarkWorkload.__fields__)
        assert set(workload_schema["required"]) == set(workload_schema["properties"])
        assert set(metrics_schema["properties"]) == set(PresetBenchmarkMetrics.__fields__)
        assert set(metrics_schema["required"]) == set(metrics_schema["properties"])
        assert set(metrics_schema["properties"]["ttft_ms"]["properties"]) == set(
            PresetBenchmarkLatency.__fields__
        )

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("failed_requests", 1, "must not include failed requests"),
            ("successful_requests", 15, "must match workload.num_requests"),
        ],
    )
    def test_rejects_inconsistent_successful_metrics(self, field, value, error):
        data = get_preset_benchmark().dict()
        data["metrics"][field] = value
        with pytest.raises(ValidationError, match=error):
            PresetBenchmark.parse_obj(data)

    def test_rejects_tool_specific_metrics(self):
        data = get_preset_benchmark().dict()
        data["metrics"]["tool_specific"] = 1

        with pytest.raises(ValidationError, match="extra fields not permitted"):
            PresetBenchmark.parse_obj(data)
