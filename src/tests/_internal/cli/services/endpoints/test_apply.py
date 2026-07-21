from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.endpoints.apply import (
    _build_service,
    _get_matching_presets,
    _select_plan,
    apply_endpoint_preset,
)
from dstack._internal.core.models.instances import InstanceAvailability
from tests._internal.cli.endpoint_presets import get_endpoint_preset

pytestmark = pytest.mark.windows


class TestGetMatchingPresets:
    def test_matches_base_model_context_and_preset(self):
        presets = [
            get_endpoint_preset(preset_id="small", context_length=4096),
            get_endpoint_preset(preset_id="large", context_length=32768),
        ]
        configuration = EndpointConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3.5-27B"},
            context_length=8192,
        )

        assert _get_matching_presets(presets, configuration=configuration, preset_id=None) == [
            presets[1]
        ]
        assert _get_matching_presets(presets, configuration=configuration, preset_id="large") == [
            presets[1]
        ]
        assert not _get_matching_presets(presets, configuration=configuration, preset_id="small")

    def test_exact_request_matches_repo_and_client_facing_name(self):
        matching = get_endpoint_preset(preset_id="matching")
        configuration = EndpointConfiguration(
            name="qwen",
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            },
        )

        assert _get_matching_presets([matching], configuration=configuration, preset_id=None) == [
            matching
        ]
        assert not _get_matching_presets(
            [matching.copy(update={"model": "other/repo"})],
            configuration=configuration,
            preset_id=None,
        )


class TestBuildService:
    def test_applies_endpoint_name_env_gateway_and_constraints(self):
        configuration = EndpointConfiguration(
            name="qwen-production",
            model={"base": "Qwen/Qwen3.5-27B"},
            gateway="inference",
            env={"HF_TOKEN": "token"},
            fleets=["gpu-fleet"],
            max_price=1,
        )

        service = _build_service(configuration, get_endpoint_preset())

        assert service.name == "qwen-production"
        assert service.gateway == "inference"
        assert service.env["HF_TOKEN"] == "token"
        assert [fleet.format() for fleet in service.fleets] == ["gpu-fleet"]
        assert service.max_price == 1


class TestSelectPlan:
    def test_selects_first_preset_with_available_offer(self):
        presets = [
            get_endpoint_preset(preset_id="unavailable"),
            get_endpoint_preset(preset_id="available"),
            get_endpoint_preset(preset_id="never-probed"),
        ]
        configurator = Mock()
        plans = [
            (_plan(InstanceAvailability.NOT_AVAILABLE), Mock()),
            (_plan(InstanceAvailability.AVAILABLE), Mock()),
        ]
        configurator.get_plan.side_effect = plans
        service_args = SimpleNamespace(profile=None)

        selected = _select_plan(
            configuration=EndpointConfiguration(name="qwen", model={"base": "Qwen/Qwen3.5-27B"}),
            configuration_path="endpoint.dstack.yml",
            presets=presets,
            configurator=configurator,
            service_args=service_args,
        )

        assert selected.preset.id == "available"
        assert selected.run_plan is plans[1][0]
        assert selected.repo is plans[1][1]
        assert configurator.get_plan.call_count == 2

    def test_applies_the_selected_plan(self, monkeypatch):
        preset = get_endpoint_preset()
        run_plan = _plan(InstanceAvailability.AVAILABLE)
        repo = Mock()
        service_args = SimpleNamespace(profile="gpu")
        configurator = Mock()
        configurator.get_parser.return_value.parse_args.return_value = service_args
        configurator.get_plan.return_value = (run_plan, repo)
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.apply.ServiceConfigurator",
            lambda api_client: configurator,
        )
        command_args = SimpleNamespace()

        apply_endpoint_preset(
            api=Mock(),
            configuration=EndpointConfiguration(
                name="qwen",
                model={"base": "Qwen/Qwen3.5-27B"},
            ),
            configuration_path="endpoint.dstack.yml",
            preset_id=None,
            profile_name="gpu",
            command_args=command_args,
            store=Mock(list=Mock(return_value=[preset])),
        )

        assert service_args.profile == "gpu"
        configurator.apply_plan.assert_called_once_with(
            run_plan=run_plan,
            repo=repo,
            command_args=command_args,
            configurator_args=service_args,
            plan_properties={
                "Model": "Qwen/Qwen3.5-27B ([secondary]base[/])",
                "Preset": "8f3a12c4 ([secondary]context=32K, con=1 42.1 tok/s TTFT 108ms[/])",
            },
        )


def _plan(availability: InstanceAvailability):
    return SimpleNamespace(
        job_plans=[SimpleNamespace(offers=[SimpleNamespace(availability=availability)])]
    )
