import pytest
from pydantic import ValidationError

from dstack._internal.cli.models.presets import (
    PresetBenchmark,
)
from tests._internal.cli.common import get_preset_benchmark

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
