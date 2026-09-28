from io import StringIO

import pytest
from rich.console import Console

import dstack._internal.cli.services.configurators.volume as volume_configurator_module
from dstack._internal.cli.services.configurators.volume import _print_plan_header
from dstack._internal.core.models.volumes import (
    DaytonaVolumeConfiguration,
    VolumeConfiguration,
    VolumePlan,
    VolumeSpec,
)


class TestPrintPlanHeader:
    def test_daytona_omits_region_and_size(self, monkeypatch: pytest.MonkeyPatch):
        output = StringIO()
        monkeypatch.setattr(volume_configurator_module, "console", Console(file=output))
        plan = VolumePlan(
            project_name="test-project",
            user="test-user",
            spec=VolumeSpec(
                configuration=DaytonaVolumeConfiguration(),
                configuration_path="volume.dstack.yml",
            ),
        )

        _print_plan_header(plan)

        rendered = " ".join(output.getvalue().split())
        assert "Backend daytona" in rendered
        assert "Region" not in rendered
        assert "Size" not in rendered

    @pytest.mark.parametrize(("size", "expected_size"), [("100GB", "100GB"), (None, "-")])
    def test_regional_volume_keeps_region_and_size(
        self, monkeypatch: pytest.MonkeyPatch, size, expected_size
    ):
        output = StringIO()
        monkeypatch.setattr(volume_configurator_module, "console", Console(file=output))
        configuration = {"backend": "aws", "region": "us-east-1", "size": size}
        if size is None:
            configuration["volume_id"] = "existing-volume"
        plan = VolumePlan(
            project_name="test-project",
            user="test-user",
            spec=VolumeSpec(
                configuration=VolumeConfiguration.model_validate(configuration).root,
                configuration_path="volume.dstack.yml",
            ),
        )

        _print_plan_header(plan)

        rendered = " ".join(output.getvalue().split())
        assert "Region us-east-1" in rendered
        assert f"Size {expected_size}" in rendered
