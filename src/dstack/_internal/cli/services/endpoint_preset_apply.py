import argparse
from dataclasses import dataclass
from typing import Optional

from rich.table import Table

from dstack._internal.cli.services.configurators.run import (
    PreparedRunConfiguration,
    ServiceConfigurator,
)
from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoint_presets import EndpointPresetRecipe
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.runs import RunPlan
from dstack.api import Client


@dataclass(frozen=True)
class _PresetPlan:
    recipe: EndpointPresetRecipe
    prepared: PreparedRunConfiguration[ServiceConfiguration]


def apply_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    configuration_path: str,
    recipe_id: Optional[str],
    profile_name: Optional[str],
    command_args: argparse.Namespace,
    store: EndpointPresetStore,
) -> None:
    recipes = _get_matching_recipes(
        store.list(),
        configuration=configuration,
        recipe_id=recipe_id,
    )
    if not recipes:
        qualifier = f" recipe {recipe_id!r}" if recipe_id else ""
        raise CLIError(
            f"No matching endpoint preset{qualifier} for {configuration.model.api_model_name}"
        )

    configurator = ServiceConfigurator(api_client=api)
    service_args = configurator.get_parser().parse_args([])
    service_args.profile = profile_name
    selected = _select_plan(
        configuration=configuration,
        configuration_path=configuration_path,
        recipes=recipes,
        configurator=configurator,
        service_args=service_args,
    )
    _print_selected_recipe(selected.recipe)
    configurator.apply_prepared_configuration(
        prepared=selected.prepared,
        command_args=command_args,
        configurator_args=service_args,
    )


def _get_matching_recipes(
    recipes: list[EndpointPresetRecipe],
    *,
    configuration: EndpointConfiguration,
    recipe_id: Optional[str],
) -> list[EndpointPresetRecipe]:
    model_name = configuration.model.api_model_name
    matches = []
    for recipe in recipes:
        service_model = recipe.service.model
        if recipe_id is not None and recipe.id != recipe_id:
            continue
        if service_model is None or service_model.name.lower() != model_name.lower():
            continue
        if configuration.context_length is not None:
            if recipe.context_length < configuration.context_length:
                continue
        if configuration.model.allows_variant_selection:
            if recipe.base.lower() != model_name.lower():
                continue
        elif recipe.model != configuration.model.exact_repo:
            continue
        matches.append(recipe)
    return matches


def _select_plan(
    *,
    configuration: EndpointConfiguration,
    configuration_path: str,
    recipes: list[EndpointPresetRecipe],
    configurator: ServiceConfigurator,
    service_args: argparse.Namespace,
) -> _PresetPlan:
    first_plan: Optional[_PresetPlan] = None
    for recipe in recipes:
        service = _build_service(configuration, recipe)
        prepared = configurator.prepare_configuration(
            conf=service,
            configuration_path=configuration_path,
            configurator_args=service_args,
        )
        plan = _PresetPlan(recipe=recipe, prepared=prepared)
        if first_plan is None:
            first_plan = plan
        if _has_available_offers(prepared.run_plan):
            return plan
    assert first_plan is not None
    return first_plan


def _build_service(
    configuration: EndpointConfiguration,
    recipe: EndpointPresetRecipe,
) -> ServiceConfiguration:
    service = recipe.service.copy(deep=True)
    service.name = configuration.name
    service.gateway = configuration.gateway
    service.env.update(configuration.env)
    for field in ProfileParams.__fields__:
        value = getattr(configuration, field)
        if value is not None:
            setattr(service, field, value)
    return service


def _has_available_offers(plan: RunPlan) -> bool:
    return bool(plan.job_plans) and all(
        any(offer.availability.is_available() for offer in job_plan.offers)
        for job_plan in plan.job_plans
    )


def _print_selected_recipe(recipe: EndpointPresetRecipe) -> None:
    table = Table(box=None, show_header=False)
    table.add_column(no_wrap=True)
    table.add_column()
    table.add_row("[bold]Preset[/]", recipe.base)
    table.add_row("[bold]Recipe[/]", recipe.id)
    console.print(table)
    console.print()
