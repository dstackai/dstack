from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.services.presets.apply import (
    _build_service,
    _validate_preset_matches,
    apply_preset,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.instances import InstanceAvailability
from tests._internal.cli.preset_factories import get_preset

pytestmark = pytest.mark.windows


class TestValidatePresetMatches:
    def test_accepts_matching_base_model_and_context(self):
        preset = get_preset(preset_id="large", context_length=32768)
        configuration = PresetConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3.5-27B"},
            context_length=8192,
        )

        _validate_preset_matches(preset, configuration=configuration)

    def test_rejects_insufficient_context(self):
        preset = get_preset(preset_id="small", context_length=4096)
        configuration = PresetConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3.5-27B"},
            context_length=8192,
        )

        with pytest.raises(CLIError, match="context length"):
            _validate_preset_matches(preset, configuration=configuration)

    def test_exact_request_matches_repo_and_client_facing_name(self):
        matching = get_preset(preset_id="matching")
        configuration = PresetConfiguration(
            name="qwen",
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            },
        )

        _validate_preset_matches(matching, configuration=configuration)
        with pytest.raises(CLIError, match="does not serve repo"):
            _validate_preset_matches(
                matching.copy(update={"model": "other/repo"}),
                configuration=configuration,
            )


class TestBuildService:
    def test_applies_preset_name_env_gateway_and_constraints(self):
        configuration = PresetConfiguration(
            name="qwen-production",
            model={"base": "Qwen/Qwen3.5-27B"},
            gateway="inference",
            env={"HF_TOKEN": "token"},
            fleets=["gpu-fleet"],
            max_price=1,
        )

        service = _build_service(configuration, get_preset())

        assert service.name == "qwen-production"
        assert service.gateway == "inference"
        assert service.env["HF_TOKEN"] == "token"
        assert [fleet.format() for fleet in service.fleets] == ["gpu-fleet"]
        assert service.max_price == 1


class TestApplyPreset:
    def test_rejects_unknown_preset(self):
        with pytest.raises(CLIError, match="does not exist"):
            apply_preset(
                api=Mock(),
                configuration=PresetConfiguration(name="qwen", model={"base": "Qwen/Qwen3.5-27B"}),
                configuration_path="preset.dstack.yml",
                preset_id="ee55ff66",
                profile_name=None,
                command_args=SimpleNamespace(),
                store=Mock(find_by_id_or_name=Mock(return_value=None)),
            )

    def test_applies_the_referenced_preset(self, monkeypatch):
        preset = get_preset()
        run_plan = _plan(InstanceAvailability.AVAILABLE)
        repo = Mock()
        service_args = SimpleNamespace(profile="gpu")
        configurator = Mock()
        configurator.get_parser.return_value.parse_args.return_value = service_args
        configurator.get_plan.return_value = (run_plan, repo)
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.apply.ServiceConfigurator",
            lambda api_client: configurator,
        )
        command_args = SimpleNamespace()

        apply_preset(
            api=Mock(),
            configuration=PresetConfiguration(
                name="qwen",
                model={"base": "Qwen/Qwen3.5-27B"},
            ),
            configuration_path="preset.dstack.yml",
            preset_id="8f3a12c4",
            profile_name="gpu",
            command_args=command_args,
            store=Mock(find_by_id_or_name=Mock(return_value=preset)),
        )

        assert service_args.profile == "gpu"
        configurator.apply_plan.assert_called_once_with(
            run_plan=run_plan,
            repo=repo,
            command_args=command_args,
            configurator_args=service_args,
            plan_properties={
                "Model": "Qwen/Qwen3.5-27B ([secondary]base[/])",
                "Preset": "8f3a12c4 ([secondary]ctx=32K con=1 42.1 tok/s TTFT 108ms[/])",
            },
        )


def _plan(availability: InstanceAvailability):
    return SimpleNamespace(
        job_plans=[SimpleNamespace(offers=[SimpleNamespace(availability=availability)])]
    )
