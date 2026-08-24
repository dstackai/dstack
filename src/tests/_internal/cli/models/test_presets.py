import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.presets import (
    PresetBenchmark,
)
from tests._internal.cli.common import SHARED_PREFIX_WORKLOAD, get_preset_benchmark

pytestmark = pytest.mark.windows


class TestPresetBenchmark:
    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("failed_requests", 1, "must not include failed requests"),
            ("successful_requests", 15, "must match workload.num_requests"),
        ],
    )
    def test_rejects_inconsistent_successful_metrics(self, field, value, error):
        data = get_preset_benchmark().model_dump()
        data["metrics"][field] = value
        with pytest.raises(ValidationError, match=error):
            PresetBenchmark.model_validate(data)

    def test_rejects_tool_specific_metrics(self):
        data = get_preset_benchmark().model_dump()
        data["metrics"]["tool_specific"] = 1

        # No `match=`: the wording is pydantic's, and v2 rewords it ("Extra inputs are not
        # permitted" rather than "extra fields not permitted"). What matters is the rejection.
        with pytest.raises(ValidationError):
            PresetBenchmark.model_validate(data)

    def test_keeps_both_a_tool_dataset_name_and_a_shared_prefix(self):
        # A synthetic workload has two facts to state: the shared prefix it was run
        # with and the name the benchmark tool gave the data it generated.
        data = get_preset_benchmark().model_dump()
        data["workload"] = dict(SHARED_PREFIX_WORKLOAD)

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset == "generated-shared-prefix"
        assert benchmark.workload.shared_prefix_tokens == 130048

    def test_reads_a_workload_stored_without_a_dataset(self):
        # Every preset written before the workload could carry a tool dataset name.
        data = get_preset_benchmark().model_dump()
        del data["workload"]["dataset"]

        benchmark = PresetBenchmark.model_validate(data)

        assert benchmark.workload.dataset is None
        assert benchmark.workload.shared_prefix_tokens == 0
