import argparse
from typing import Optional

from rich.markup import escape

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.presets import Preset
from dstack._internal.cli.services.configurators.run import ServiceConfigurator
from dstack._internal.cli.services.presets.output import (
    format_preset_benchmark,
)
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack.api import Client


def apply_preset(
    *,
    api: Client,
    configuration: PresetConfiguration,
    configuration_path: str,
    preset_id: str,
    profile_name: Optional[str],
    command_args: argparse.Namespace,
    store: PresetStore,
) -> None:
    preset = store.get(preset_id)
    if preset is None:
        raise CLIError(f"Preset {preset_id} does not exist")
    _validate_preset_matches(preset, configuration=configuration)

    configurator = ServiceConfigurator(api_client=api)
    service_args = configurator.get_parser().parse_args([])
    service_args.profile = profile_name
    service = _build_service(configuration, preset)
    run_plan, repo = configurator.get_plan(
        conf=service,
        configuration_path=configuration_path,
        configurator_args=service_args,
    )
    configurator.apply_plan(
        run_plan=run_plan,
        repo=repo,
        command_args=command_args,
        configurator_args=service_args,
        plan_properties={
            "Model": _format_requested_model(configuration),
            "Preset": _format_selected_preset(preset),
        },
    )


def _validate_preset_matches(preset: Preset, *, configuration: PresetConfiguration) -> None:
    """The referenced preset must serve what the configuration asks for."""
    model_name = configuration.model.api_model_name
    service_model = preset.service.model
    if service_model is None or service_model.name.lower() != model_name.lower():
        raise CLIError(f"Preset {preset.id} does not serve {model_name}")
    if configuration.context_length is not None:
        if preset.context_length < configuration.context_length:
            raise CLIError(
                f"Preset {preset.id} does not support context length"
                f" {configuration.context_length}"
            )
    if configuration.model.allows_variant_selection:
        if preset.base.lower() != model_name.lower():
            raise CLIError(f"Preset {preset.id} does not serve base model {model_name}")
    elif preset.model != configuration.model.exact_repo:
        raise CLIError(f"Preset {preset.id} does not serve repo {configuration.model.exact_repo}")


def _build_service(
    configuration: PresetConfiguration,
    preset: Preset,
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


def _format_requested_model(configuration: PresetConfiguration) -> str:
    model = escape(configuration.model.api_model_name)
    if configuration.model.allows_variant_selection:
        return f"{model} ([secondary]base[/])"
    return model


def _format_selected_preset(preset: Preset) -> str:
    details = format_preset_benchmark(preset, verbose=True)
    return f"{escape(preset.id)} ([secondary]{details}[/])"
