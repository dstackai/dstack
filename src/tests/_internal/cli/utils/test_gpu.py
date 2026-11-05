import json
from unittest.mock import patch

import gpuhunt
import pytest
from rich.console import Console

from dstack._internal.cli.utils.gpu import print_gpu_json, print_gpu_table
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gpus import GpuGroup
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.resources import Range
from dstack._internal.server.testing.common import get_run_spec


def _get_group(availability: list[InstanceAvailability]) -> GpuGroup:
    return GpuGroup(
        name="H200",
        memory_mib=144384,
        vendor=gpuhunt.AcceleratorVendor.NVIDIA,
        count=Range[int](min=8, max=8),
        price=Range[float](min=2, max=2),
        availability=availability,
        spot=["on-demand"],
        backends=[BackendType.NEBIUS],
    )


class TestPrintGpuTable:
    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            (["available"], "available"),
            (["unknown"], "unknown"),
            (["unknown", "available", "unknown"], "available, unknown"),
            (["not_available", "no_quota", "not_available"], "no quota, not available"),
            (["no_quota", "available"], "available, no quota"),
            (["no_balance", "unknown"], "no balance, unknown"),
        ],
    )
    def test_displays_complete_sorted_set(self, statuses, expected):
        console = Console(width=200, color_system=None)
        with (
            patch("dstack._internal.cli.utils.gpu.console", console),
            console.capture() as capture,
        ):
            print_gpu_table(
                [_get_group([InstanceAvailability(status) for status in statuses])],
                get_run_spec(repo_id="test-repo"),
                ["gpu"],
                "main",
            )

        assert expected in capture.get()


class TestPrintGpuJson:
    def test_keeps_availability_as_a_list(self, capsys):
        group = _get_group([InstanceAvailability.NO_QUOTA, InstanceAvailability.NOT_AVAILABLE])
        print_gpu_json([group], get_run_spec(repo_id="test-repo"), ["gpu"], "main")

        output = json.loads(capsys.readouterr().out)
        assert output["gpus"][0]["availability"] == ["no_quota", "not_available"]
        assert "status" not in output["gpus"][0]
