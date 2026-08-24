import argparse
from pathlib import Path

from dstack._internal.cli.services.configurators.base import (
    APPLY_STDIN_NAME,
    ArgsParser,
    BaseApplyConfigurator,
)
from dstack._internal.cli.services.presets.create import (
    CreationStopped,
    create_preset,
    find_preset_name_holders,
    plan_preset,
    reassign_preset_name,
    resolve_previous_sessions,
)
from dstack._internal.cli.services.presets.store import (
    PresetStore,
    resolve_preset_prompt,
)
from dstack._internal.cli.services.profile import (
    apply_profile_args,
    load_profile_from_args,
    register_profile_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import CLIError, ConfigurationError, ServerClientError
from dstack._internal.core.models.configurations import ApplyConfigurationType, PresetConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.services import validate_dstack_resource_name


class PresetConfigurator(BaseApplyConfigurator[PresetConfiguration]):
    TYPE = ApplyConfigurationType.PRESET

    def apply_configuration(
        self,
        conf: PresetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
        configurator_args: argparse.Namespace,
    ):
        if command_args.detach:
            raise CLIError("-d/--detach is not supported for preset configurations")
        conf = self.apply_args(conf, configurator_args)
        user_prompt = resolve_preset_prompt(conf, _configuration_prompt_base(configuration_path))
        store = PresetStore()
        previous = ()
        if conf.previous:
            previous = resolve_previous_sessions(conf.previous)
        if conf.trials is None:
            raise ConfigurationError(
                "trials is required. Set it in the configuration or pass --trials"
            )
        for field in ("max_ttft", "min_context_length", "concurrency"):
            if getattr(conf, field) is None:
                raise ConfigurationError(f"{field} is required")
        allowed_fleets = plan_preset(api=self.api, configuration=conf)
        if not _confirm_preset_creation(store, conf.name, assume_yes=command_args.yes):
            console.print("\nExiting...")
            return
        try:
            result = create_preset(
                api=self.api,
                configuration=conf,
                store=store,
                keep_service=configurator_args.keep_service,
                user_prompt=user_prompt,
                allowed_fleets=allowed_fleets,
                previous=previous,
            )
        except KeyboardInterrupt:
            return  # the interrupt handler already reported detach / stop
        except CreationStopped:
            return  # stopped from another CLI, which reported the interruption
        # The log already told the story; like a finished run, success is silent.
        if configurator_args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def delete_configuration(
        self,
        conf: PresetConfiguration,
        configuration_path: str,
        command_args: argparse.Namespace,
    ):
        raise CLIError(
            "Deleting a preset configuration is not supported. Use `dstack preset delete <ID>`"
        )

    @classmethod
    def register_args(cls, parser: argparse.ArgumentParser):
        configuration_group = parser.add_argument_group(f"{cls.TYPE.value} Options")
        configuration_group.add_argument(
            "-n",
            "--name",
            dest="name",
            help="The preset name",
        )
        register_creation_args(configuration_group)
        register_profile_args(parser)

    def apply_args(
        self, conf: PresetConfiguration, args: argparse.Namespace
    ) -> PresetConfiguration:
        _apply_name(conf, args.name)
        if getattr(args, "trials", None) is not None:
            conf.trials = args.trials
        if getattr(args, "previous", None):
            conf.previous = list(args.previous)
        profile = load_profile_from_args(args=args, repo_dir=Path.cwd())
        for field in ProfileParams.model_fields:
            if getattr(conf, field) is None:
                setattr(conf, field, getattr(profile, field))
        apply_profile_args(args, conf)
        # A revalidated copy rather than the mutated input: merging the profile
        # has to re-run the model validators.
        return PresetConfiguration.model_validate(conf.model_dump())


def register_creation_args(parser: ArgsParser) -> None:
    parser.add_argument(
        "--keep-service",
        action="store_true",
        help="Leave the verified service running",
    )
    parser.add_argument(
        "--trials",
        type=int,
        metavar="N",
        help="The number of benchmarked trials before the best one is promoted",
    )
    parser.add_argument(
        "--previous",
        action="append",
        metavar="ID",
        help="Give the agent a previous session's results to analyze and improve on."
        " Repeat for several",
    )


def _configuration_prompt_base(configuration_file: str) -> Path:
    """Prompt files resolve relative to the configuration file; cwd for stdin."""
    if configuration_file == APPLY_STDIN_NAME:
        return Path.cwd()
    return Path(configuration_file).resolve().parent


def _apply_name(configuration: PresetConfiguration, name: str | None) -> None:
    if name is not None:
        configuration.name = name
    if configuration.name is None:
        return
    try:
        validate_dstack_resource_name(configuration.name)
    except ServerClientError as e:
        raise CLIError(str(e)) from e


def _confirm_preset_creation(store: PresetStore, name: str | None, *, assume_yes: bool) -> bool:
    """One apply-style confirmation; reassigns the name from any holder on yes."""
    holders = find_preset_name_holders(store, name) if name is not None else None
    if holders is not None and holders.preset_ids:
        used_by = ", ".join(f"preset [code]{preset_id}[/]" for preset_id in holders.preset_ids)
        message = (
            f"The name [code]{name}[/] is already used by {used_by}. Reassign it to a new preset?"
        )
    elif name is not None:
        message = f"Create the preset [code]{name}[/]?"
    else:
        message = "Create the preset?"
    if not assume_yes and not confirm_ask(message):
        return False
    if holders is not None:
        reassign_preset_name(store, holders)
    return True
