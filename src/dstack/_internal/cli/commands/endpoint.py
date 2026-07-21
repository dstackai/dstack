import argparse
import os
import time
from pathlib import Path

from argcomplete import FilesCompleter  # type: ignore[attr-defined]

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.models.endpoint_presets import (
    EndpointPreset,
    EndpointPresetListOutput,
)
from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.services.endpoints.agent import (
    list_agent_sessions,
    load_resumable_agent_session,
)
from dstack._internal.cli.services.endpoints.apply import apply_endpoint_preset
from dstack._internal.cli.services.endpoints.create import create_endpoint_preset
from dstack._internal.cli.services.endpoints.output import print_endpoint_presets
from dstack._internal.cli.services.endpoints.store import (
    EndpointPresetStore,
    load_endpoint_configuration,
    resolve_endpoint_prompt,
)
from dstack._internal.cli.services.profile import apply_profile_args, register_profile_args
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.services import is_valid_dstack_resource_name
from dstack.api import Client
from dstack.api.utils import load_profile


class EndpointCommand(BaseCommand):
    NAME = "preset"
    DESCRIPTION = "Manage model serving presets"

    def _register(self) -> None:
        self._parser.add_argument(
            "--project",
            help="The name of the project. Defaults to [code]$DSTACK_PROJECT[/]",
            metavar="NAME",
            default=os.getenv("DSTACK_PROJECT"),
        ).completer = ProjectNameCompleter()  # type: ignore[attr-defined]
        _add_list_args(self._parser)
        self._parser.set_defaults(subfunc=self._list)
        preset_subparsers = self._parser.add_subparsers(dest="action")

        list_parser = preset_subparsers.add_parser(
            "list",
            help="List presets",
            formatter_class=self._parser.formatter_class,
        )
        _add_list_args(list_parser)
        list_parser.set_defaults(subfunc=self._list)

        get_parser = preset_subparsers.add_parser(
            "get",
            help="Get a preset",
            formatter_class=self._parser.formatter_class,
        )
        get_parser.add_argument("preset", metavar="ID", help="The preset ID")
        get_parser.add_argument(
            "--json",
            action="store_true",
            required=True,
            help="Output in JSON format",
        )
        get_parser.set_defaults(subfunc=self._get)

        create_parser = preset_subparsers.add_parser(
            "create",
            help="Create a preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(create_parser)
        register_profile_args(create_parser)
        create_parser.add_argument(
            "--keep-service",
            action="store_true",
            help="Leave the verified service running",
        )
        create_parser.add_argument(
            "--max-trials",
            type=int,
            metavar="N",
            help="The maximum number of benchmarked trials before the best one is promoted",
        )
        create_parser.add_argument(
            "--debug",
            action="store_true",
            help="Save the agent prompt and raw trace",
        )
        create_parser.add_argument(
            "--resume",
            metavar="ID",
            help="Resume an interrupted preset creation session by its preset ID",
        )
        create_parser.set_defaults(subfunc=self._create)

        apply_parser = preset_subparsers.add_parser(
            "apply",
            help="Apply a preset",
            formatter_class=self._parser.formatter_class,
        )
        _add_configuration_args(apply_parser)
        register_profile_args(apply_parser)
        apply_parser.add_argument(
            "--id",
            action="append",
            dest="preset_ids",
            metavar="ID",
            help="Deploy the best available preset among these IDs. Can be repeated",
        )
        apply_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        apply_parser.add_argument(
            "--force", action="store_true", help="Force apply when no changes are detected"
        )
        apply_parser.add_argument(
            "-d", "--detach", action="store_true", help="Exit after submitting the service"
        )
        apply_parser.add_argument(
            "-v", "--verbose", action="store_true", help="Show all plan properties"
        )
        apply_parser.set_defaults(subfunc=self._apply)

        delete_parser = preset_subparsers.add_parser(
            "delete",
            help="Delete presets",
            formatter_class=self._parser.formatter_class,
        )
        delete_target = delete_parser.add_mutually_exclusive_group(required=True)
        delete_target.add_argument(
            "preset",
            nargs="?",
            metavar="ID",
            help="The preset ID",
        )
        delete_target.add_argument(
            "--base",
            metavar="MODEL",
            help="Delete all presets for a base model",
        )
        delete_target.add_argument(
            "--repo",
            metavar="REPO",
            help="Delete all presets serving a model repo",
        )
        delete_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        delete_parser.set_defaults(subfunc=self._delete)

    def _command(self, args: argparse.Namespace) -> None:
        super()._command(args)
        try:
            args.subfunc(args)
        except KeyboardInterrupt:
            console.print("\nOperation interrupted by user. Exiting...")
            exit(0)

    def _list(self, args: argparse.Namespace) -> None:
        base = getattr(args, "base", None)
        repo = getattr(args, "repo", None)
        if getattr(args, "json", False):
            presets = _filter_presets(EndpointPresetStore().list(), base=base, repo=repo)
            print(EndpointPresetListOutput(presets=presets).json())
            return
        verbose = getattr(args, "verbose", False)
        while True:
            presets = EndpointPresetStore().list()
            sessions = list_agent_sessions()
            if base or repo:
                repo_to_base = {preset.model: preset.base for preset in presets}
                presets = _filter_presets(presets, base=base, repo=repo)
                sessions = [
                    session
                    for session in sessions
                    if _session_matches_model(
                        session, base=base, repo=repo, repo_to_base=repo_to_base
                    )
                ]
            if getattr(args, "watch", False):
                console.clear()
            print_endpoint_presets(presets, sessions=sessions, verbose=verbose)
            if not getattr(args, "watch", False):
                return
            time.sleep(5)

    def _create(self, args: argparse.Namespace) -> None:
        configuration_path, configuration = load_endpoint_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args)
        user_prompt = resolve_endpoint_prompt(configuration, configuration_path)
        resume_session = None
        if getattr(args, "resume", None):
            resume_session = load_resumable_agent_session(args.resume)
            if getattr(args, "max_trials", None) is not None:
                console.print(
                    "[warning]--max-trials is ignored when resuming: "
                    "session constraints are fixed at creation[/]"
                )
        result = create_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            store=EndpointPresetStore(),
            keep_service=args.keep_service,
            debug=args.debug,
            resume_session=resume_session,
            user_prompt=user_prompt,
        )
        console.print(
            f"Preset [code]{result.preset.id}[/] for "
            f"[code]{result.preset.base}[/] saved to [code]{result.path}[/]"
        )
        if args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _get(self, args: argparse.Namespace) -> None:
        preset = EndpointPresetStore().get(args.preset)
        if preset is None:
            raise CLIError(f"Preset {args.preset!r} does not exist")
        print(preset.json())

    def _apply(self, args: argparse.Namespace) -> None:
        configuration_path, configuration = load_endpoint_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args)
        apply_endpoint_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            configuration_path=configuration_path,
            preset_ids=args.preset_ids,
            profile_name=args.profile,
            command_args=args,
            store=EndpointPresetStore(),
        )

    def _delete(self, args: argparse.Namespace) -> None:
        store = EndpointPresetStore()
        if args.preset is not None:
            preset = store.get(args.preset)
            if preset is None:
                raise CLIError(f"Preset {args.preset!r} does not exist")
            presets = [preset]
            message = f"Delete preset [code]{preset.id}[/] for [code]{preset.base}[/]?"
        else:
            target = args.base or args.repo
            presets = _filter_presets(store.list(), base=args.base, repo=args.repo)
            if not presets:
                kind = "base model" if args.base else "model repo"
                raise CLIError(f"No presets found for {kind} {target!r}")
            message = (
                f"Delete {len(presets)} preset"
                f"{'s' if len(presets) != 1 else ''} for [code]{target}[/]?"
            )
        if not args.yes and not confirm_ask(message):
            console.print("\nExiting...")
            return
        for preset in presets:
            store.delete(preset.id)
        if args.preset is not None:
            console.print(
                f"Preset [code]{presets[0].id}[/] for [code]{presets[0].base}[/] deleted"
            )
        else:
            console.print(
                f"Deleted {len(presets)} preset{'s' if len(presets) != 1 else ''} "
                f"for [code]{args.base or args.repo}[/]"
            )


def _add_configuration_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-f",
        "--file",
        required=True,
        metavar="FILE",
        dest="configuration_file",
        help="The preset configuration file",
    ).completer = FilesCompleter(allowednames=["*.yml", "*.yaml"])  # type: ignore[attr-defined]
    parser.add_argument(
        "-n",
        "--name",
        metavar="NAME",
        help="The service name. Required when the configuration omits name",
    )


def _add_list_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "-w",
        "--watch",
        action="store_true",
        help="Watch presets and sessions in realtime",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    model_filter = parser.add_mutually_exclusive_group()
    model_filter.add_argument(
        "--base",
        metavar="MODEL",
        help="Show only presets for a base model",
    )
    model_filter.add_argument(
        "--repo",
        metavar="REPO",
        help="Show only presets serving a model repo",
    )


def _filter_presets(
    presets: list[EndpointPreset],
    *,
    base: str | None,
    repo: str | None,
) -> list[EndpointPreset]:
    return [
        preset
        for preset in presets
        if (base is None or preset.base == base) and (repo is None or preset.model == repo)
    ]


def _session_matches_model(
    session: dict,
    *,
    base: str | None,
    repo: str | None,
    repo_to_base: dict[str, str],
) -> bool:
    model = str(session.get("model") or "")
    if not model:
        return False
    if repo is not None:
        return model == repo
    return model == base or repo_to_base.get(model) == base


def _apply_name(configuration: EndpointConfiguration, name: str | None) -> None:
    if name is not None:
        configuration.name = name
    if configuration.name is None:
        raise CLIError(
            "The service name is required. Set `name` in the configuration or use --name"
        )
    if not is_valid_dstack_resource_name(configuration.name):
        raise CLIError("The name must match '^[a-z][a-z0-9-]{1,40}$'")


def _get_effective_configuration(
    configuration: EndpointConfiguration,
    args: argparse.Namespace,
) -> EndpointConfiguration:
    _apply_name(configuration, args.name)
    if getattr(args, "max_trials", None) is not None:
        configuration.max_trials = args.max_trials
    profile = load_profile(Path.cwd(), args.profile)
    for field in ProfileParams.__fields__:
        if getattr(configuration, field) is None:
            setattr(configuration, field, getattr(profile, field))
    apply_profile_args(args, configuration)
    return EndpointConfiguration.parse_obj(configuration.dict())
