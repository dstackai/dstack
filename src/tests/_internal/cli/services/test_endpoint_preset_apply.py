from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dstack._internal.cli.services.endpoint_preset_apply import (
    _build_service,
    _get_matching_recipes,
    _select_plan,
    apply_endpoint_preset,
)
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.instances import InstanceAvailability
from tests._internal.cli.endpoint_presets import get_endpoint_preset_recipe

pytestmark = pytest.mark.windows


class TestGetMatchingRecipes:
    def test_matches_base_model_context_and_recipe(self):
        recipes = [
            get_endpoint_preset_recipe(recipe_id="small", context_length=4096),
            get_endpoint_preset_recipe(recipe_id="large", context_length=32768),
        ]
        configuration = EndpointConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3.5-27B"},
            context_length=8192,
        )

        assert _get_matching_recipes(recipes, configuration=configuration, recipe_id=None) == [
            recipes[1]
        ]
        assert _get_matching_recipes(recipes, configuration=configuration, recipe_id="large") == [
            recipes[1]
        ]
        assert not _get_matching_recipes(recipes, configuration=configuration, recipe_id="small")

    def test_exact_request_matches_repo_and_client_facing_name(self):
        matching = get_endpoint_preset_recipe(recipe_id="matching")
        configuration = EndpointConfiguration(
            name="qwen",
            model={
                "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                "name": "Qwen/Qwen3.5-27B",
            },
        )

        assert _get_matching_recipes([matching], configuration=configuration, recipe_id=None) == [
            matching
        ]
        assert not _get_matching_recipes(
            [matching.copy(update={"model": "other/repo"})],
            configuration=configuration,
            recipe_id=None,
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

        service = _build_service(configuration, get_endpoint_preset_recipe())

        assert service.name == "qwen-production"
        assert service.gateway == "inference"
        assert service.env["HF_TOKEN"] == "token"
        assert [fleet.format() for fleet in service.fleets] == ["gpu-fleet"]
        assert service.max_price == 1


class TestSelectPlan:
    def test_selects_first_recipe_with_available_offer(self):
        recipes = [
            get_endpoint_preset_recipe(recipe_id="unavailable"),
            get_endpoint_preset_recipe(recipe_id="available"),
        ]
        configurator = Mock()
        prepared = [
            Mock(run_plan=_plan(InstanceAvailability.NOT_AVAILABLE)),
            Mock(run_plan=_plan(InstanceAvailability.AVAILABLE)),
        ]
        configurator.prepare_configuration.side_effect = prepared
        service_args = SimpleNamespace(profile=None)

        selected = _select_plan(
            configuration=EndpointConfiguration(name="qwen", model={"base": "Qwen/Qwen3.5-27B"}),
            configuration_path="endpoint.dstack.yml",
            recipes=recipes,
            configurator=configurator,
            service_args=service_args,
        )

        assert selected.recipe.id == "available"
        assert selected.prepared is prepared[1]
        assert configurator.prepare_configuration.call_count == 2

    def test_applies_the_selected_prepared_plan(self, monkeypatch):
        recipe = get_endpoint_preset_recipe()
        prepared = Mock(run_plan=_plan(InstanceAvailability.AVAILABLE))
        configurator = Mock()
        configurator.get_parser.return_value.parse_args.return_value = SimpleNamespace()
        configurator.prepare_configuration.return_value = prepared
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_apply.ServiceConfigurator",
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
            recipe_id=None,
            profile_name="gpu",
            command_args=command_args,
            store=Mock(list=Mock(return_value=[recipe])),
        )

        assert configurator.get_parser.return_value.parse_args.return_value.profile == "gpu"
        configurator.apply_prepared_configuration.assert_called_once_with(
            prepared=prepared,
            command_args=command_args,
            configurator_args=configurator.get_parser.return_value.parse_args.return_value,
            plan_properties={"Preset": "Qwen/Qwen3.5-27B ([secondary]recipe=8f3a12c4[/])"},
        )


def _plan(availability: InstanceAvailability):
    return SimpleNamespace(
        job_plans=[SimpleNamespace(offers=[SimpleNamespace(availability=availability)])]
    )
