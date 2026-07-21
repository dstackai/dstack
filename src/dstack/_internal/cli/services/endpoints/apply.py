import argparse
from dataclasses import dataclass
from typing import Optional, Sequence

from rich.markup import escape

from dstack._internal.cli.models.endpoint_presets import EndpointPreset
from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.configurators.run import ServiceConfigurator
from dstack._internal.cli.services.endpoints.output import (
    format_endpoint_benchmark,
)
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.repos.base import Repo
from dstack._internal.core.models.runs import RunPlan
from dstack.api import Client


@dataclass(frozen=True)
class _PresetPlan:
    preset: EndpointPreset
    run_plan: RunPlan
    repo: Repo


def apply_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    configuration_path: str,
    preset_ids: Optional[Sequence[str]],
    profile_name: Optional[str],
    command_args: argparse.Namespace,
    store: EndpointPresetStore,
) -> None:
    candidates = _get_candidate_presets(store.list(), preset_ids=preset_ids)
    presets = _get_matching_presets(candidates, configuration=configuration)
    if not presets:
        qualifier = ""
        if preset_ids:
            qualifier = f" among {', '.join(preset_ids)}"
        raise CLIError(f"No matching preset{qualifier} for {configuration.model.api_model_name}")

    configurator = ServiceConfigurator(api_client=api)
    service_args = configurator.get_parser().parse_args([])
    service_args.profile = profile_name
    selected = _select_plan(
        configuration=configuration,
        configuration_path=configuration_path,
        presets=presets,
        configurator=configurator,
        service_args=service_args,
    )
    configurator.apply_plan(
        run_plan=selected.run_plan,
        repo=selected.repo,
        command_args=command_args,
        configurator_args=service_args,
        plan_properties={
            "Model": _format_requested_model(configuration),
            "Preset": _format_selected_preset(selected.preset),
        },
    )


def _get_candidate_presets(
    presets: list[EndpointPreset],
    *,
    preset_ids: Optional[Sequence[str]],
) -> list[EndpointPreset]:
    if not preset_ids:
        return presets
    presets_by_id = {preset.id: preset for preset in presets}
    missing = [preset_id for preset_id in preset_ids if preset_id not in presets_by_id]
    if len(missing) == 1:
        raise CLIError(f"Preset {missing[0]} does not exist")
    if missing:
        raise CLIError(f"Presets {', '.join(missing)} do not exist")
    # Preserve the order given: capacity-aware selection tries ids in turn.
    return [presets_by_id[preset_id] for preset_id in preset_ids]


def _get_matching_presets(
    presets: list[EndpointPreset],
    *,
    configuration: EndpointConfiguration,
) -> list[EndpointPreset]:
    model_name = configuration.model.api_model_name
    matches = []
    for preset in presets:
        service_model = preset.service.model
        if service_model is None or service_model.name.lower() != model_name.lower():
            continue
        if configuration.context_length is not None:
            if preset.context_length < configuration.context_length:
                continue
        if configuration.model.allows_variant_selection:
            if preset.base.lower() != model_name.lower():
                continue
        elif preset.model != configuration.model.exact_repo:
            continue
        matches.append(preset)
    return matches


def _select_plan(
    *,
    configuration: EndpointConfiguration,
    configuration_path: str,
    presets: list[EndpointPreset],
    configurator: ServiceConfigurator,
    service_args: argparse.Namespace,
) -> _PresetPlan:
    first_plan: Optional[_PresetPlan] = None
    for preset in presets:
        service = _build_service(configuration, preset)
        run_plan, repo = configurator.get_plan(
            conf=service,
            configuration_path=configuration_path,
            configurator_args=service_args,
        )
        plan = _PresetPlan(preset=preset, run_plan=run_plan, repo=repo)
        if first_plan is None:
            first_plan = plan
        if _has_available_offers(run_plan):
            return plan
    assert first_plan is not None
    return first_plan


def _build_service(
    configuration: EndpointConfiguration,
    preset: EndpointPreset,
) -> ServiceConfiguration:
    service = preset.service.copy(deep=True)
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


def _format_requested_model(configuration: EndpointConfiguration) -> str:
    model = escape(configuration.model.api_model_name)
    if configuration.model.allows_variant_selection:
        return f"{model} ([secondary]base[/])"
    return model


def _format_selected_preset(preset: EndpointPreset) -> str:
    details = format_endpoint_benchmark(preset, verbose=True)
    return f"{escape(preset.id)} ([secondary]{details}[/])"
