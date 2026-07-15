import argparse
from dataclasses import dataclass
from typing import Optional

from rich.markup import escape

from dstack._internal.cli.services.configurators.run import (
    PreparedRunConfiguration,
    ServiceConfigurator,
)
from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from dstack._internal.cli.utils.endpoint_presets import (
    format_endpoint_benchmark,
    format_endpoint_context_length,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoint_presets import EndpointPreset
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.runs import RunPlan
from dstack.api import Client


@dataclass(frozen=True)
class _PresetPlan:
    preset: EndpointPreset
    prepared: PreparedRunConfiguration[ServiceConfiguration]


def apply_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    configuration_path: str,
    preset_id: Optional[str],
    profile_name: Optional[str],
    command_args: argparse.Namespace,
    store: EndpointPresetStore,
) -> None:
    presets = _get_matching_presets(
        store.list(),
        configuration=configuration,
        preset_id=preset_id,
    )
    if not presets:
        qualifier = f" preset {preset_id!r}" if preset_id else ""
        raise CLIError(
            f"No matching endpoint preset{qualifier} for {configuration.model.api_model_name}"
        )

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
    configurator.apply_prepared_configuration(
        prepared=selected.prepared,
        command_args=command_args,
        configurator_args=service_args,
        plan_properties={
            "Model": _format_requested_model(configuration),
            "Preset": _format_selected_preset(selected.preset),
        },
    )


def _get_matching_presets(
    presets: list[EndpointPreset],
    *,
    configuration: EndpointConfiguration,
    preset_id: Optional[str],
) -> list[EndpointPreset]:
    model_name = configuration.model.api_model_name
    matches = []
    for preset in presets:
        service_model = preset.service.model
        if preset_id is not None and preset.id != preset_id:
            continue
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
        prepared = configurator.prepare_configuration(
            conf=service,
            configuration_path=configuration_path,
            configurator_args=service_args,
        )
        plan = _PresetPlan(preset=preset, prepared=prepared)
        if first_plan is None:
            first_plan = plan
        if _has_available_offers(prepared.run_plan):
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
    details = (
        f"context={format_endpoint_context_length(preset)}, {format_endpoint_benchmark(preset)}"
    )
    return f"{escape(preset.id)} ([secondary]{details}[/])"
