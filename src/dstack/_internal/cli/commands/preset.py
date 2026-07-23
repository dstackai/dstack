import argparse
import os
import time
from contextlib import suppress
from pathlib import Path

from argcomplete import FilesCompleter  # type: ignore[attr-defined]

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.presets import (
    Preset,
    PresetListOutput,
)
from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.services.presets.agent import (
    find_session_name_claims,
    get_presets_dir,
    list_agent_sessions,
    load_resumable_agent_session,
)
from dstack._internal.cli.services.presets.apply import apply_preset
from dstack._internal.cli.services.presets.create import (
    create_preset,
    plan_preset,
    reconcile_detached_sessions,
    show_preset_session_logs,
    stop_preset_session,
)
from dstack._internal.cli.services.presets.output import print_presets
from dstack._internal.cli.services.presets.store import (
    PresetStore,
    load_preset_configuration,
    resolve_preset_prompt,
)
from dstack._internal.cli.services.profile import (
    apply_profile_args,
    load_profile_from_args,
    register_profile_args,
)
from dstack._internal.cli.utils.common import confirm_ask, console, warn
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.services import is_valid_dstack_resource_name
from dstack.api import Client


class PresetCommand(BaseCommand):
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
        get_parser.add_argument("preset", metavar="ID", help="The preset ID or name")
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
            help="Resume an interrupted preset creation by its preset ID",
        )
        create_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        create_parser.set_defaults(subfunc=self._create)

        logs_parser = preset_subparsers.add_parser(
            "logs",
            help="Show a preset's creation log",
            formatter_class=self._parser.formatter_class,
        )
        logs_parser.add_argument("preset", metavar="ID", help="The preset ID or name")
        logs_parser.add_argument(
            "-f",
            "--follow",
            action="store_true",
            help="Follow to completion and save the preset",
        )
        logs_parser.add_argument(
            "--keep-service",
            action="store_true",
            help="Leave the verified service running (with -f)",
        )
        logs_parser.set_defaults(subfunc=self._logs)

        stop_parser = preset_subparsers.add_parser(
            "stop",
            help="Stop a running preset creation",
            formatter_class=self._parser.formatter_class,
        )
        stop_parser.add_argument("preset", metavar="ID", help="The preset ID or name")
        stop_parser.add_argument(
            "-y", "--yes", action="store_true", help="Do not ask for confirmation"
        )
        stop_parser.set_defaults(subfunc=self._stop)

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
            help="Deploy the best available preset among these IDs or names. Can be repeated",
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
            help="The preset ID or name",
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

    def _reconcile(self) -> None:
        """Finalize any detached/orphaned session whose agent already completed,
        so a saved preset never depends on a foreground CLI surviving. Fully
        best-effort — it must never make a read command fail."""
        with suppress(Exception):
            reconcile_detached_sessions(PresetStore())

    def _list(self, args: argparse.Namespace) -> None:
        base = args.base
        repo = args.repo
        if args.json:
            self._reconcile()
            presets = _filter_presets(PresetStore().list(), base=base, repo=repo)
            print(PresetListOutput(presets=presets).json())
            return
        verbose = args.verbose
        while True:
            self._reconcile()
            presets = PresetStore().list()
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
            print_presets(presets, sessions=sessions, verbose=verbose)
            if not getattr(args, "watch", False):
                return
            time.sleep(5)

    def _create(self, args: argparse.Namespace) -> None:
        configuration_path, configuration = load_preset_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args, require_name=False)
        user_prompt = resolve_preset_prompt(configuration, configuration_path)
        store = PresetStore()
        resume_session = None
        if getattr(args, "resume", None):
            resume_session = load_resumable_agent_session(args.resume)
            if getattr(args, "max_trials", None) is not None:
                console.print(
                    "[warning]--max-trials is ignored when resuming: "
                    "the constraints are fixed at creation[/]"
                )
        api = Client.from_config(project_name=args.project)
        allowed_fleets = None
        if resume_session is None:
            if configuration.max_trials is None:
                raise ConfigurationError(
                    "max_trials is required. Set it in the configuration or pass --max-trials"
                )
            allowed_fleets = plan_preset(api=api, configuration=configuration)
            if not _confirm_preset_creation(store, configuration.name, assume_yes=args.yes):
                console.print("\nExiting...")
                return
        try:
            result = create_preset(
                api=api,
                configuration=configuration,
                store=store,
                keep_service=args.keep_service,
                debug=args.debug,
                resume_session=resume_session,
                user_prompt=user_prompt,
                allowed_fleets=allowed_fleets,
            )
        except KeyboardInterrupt:
            return  # the interrupt handler already reported detach / stop
        console.print(f"Preset [code]{result.preset.id}[/] saved")
        if args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _logs(self, args: argparse.Namespace) -> None:
        try:
            result = show_preset_session_logs(
                project=args.project,
                store=PresetStore(),
                preset_id=_resolve_session_ref(args.preset),
                follow=args.follow,
                keep_service=args.keep_service,
            )
        except KeyboardInterrupt:
            return  # a log viewer: Ctrl+C just stops watching, quietly
        if result is not None:
            console.print(f"Preset [code]{result.preset.id}[/] saved")
            if args.keep_service:
                console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _stop(self, args: argparse.Namespace) -> None:
        preset_id = _resolve_session_ref(args.preset)
        if not args.yes and not confirm_ask(f"Stop creating preset [code]{preset_id}[/]?"):
            console.print("\nExiting...")
            return
        stop_preset_session(Client.from_config(project_name=args.project), preset_id)

    def _get(self, args: argparse.Namespace) -> None:
        self._reconcile()
        store = PresetStore()
        preset = store.get(args.preset) or store.find_by_name(args.preset)
        if preset is None:
            raise CLIError(f"Preset {args.preset!r} does not exist")
        print(preset.json())

    def _apply(self, args: argparse.Namespace) -> None:
        self._reconcile()
        configuration_path, configuration = load_preset_configuration(args.configuration_file)
        configuration = _get_effective_configuration(configuration, args)
        apply_preset(
            api=Client.from_config(project_name=args.project),
            configuration=configuration,
            configuration_path=configuration_path,
            preset_ids=args.preset_ids,
            profile_name=args.profile,
            command_args=args,
            store=PresetStore(),
        )

    def _delete(self, args: argparse.Namespace) -> None:
        store = PresetStore()
        if args.preset is not None:
            try:
                preset = store.get(args.preset) or store.find_by_name(args.preset)
            except CLIError as e:
                # A corrupt preset file must still be removable by ID.
                warn(str(e), stderr=True)
                preset_ids = [args.preset]
                description = f"preset [code]{args.preset}[/]"
            else:
                if preset is None:
                    raise CLIError(f"Preset {args.preset!r} does not exist")
                preset_ids = [preset.id]
                description = f"preset [code]{preset.id}[/] for [code]{preset.base}[/]"
        else:
            target = args.base or args.repo
            presets = _filter_presets(store.list(), base=args.base, repo=args.repo)
            if not presets:
                kind = "base model" if args.base else "model repo"
                raise CLIError(f"No presets found for {kind} {target!r}")
            preset_ids = [preset.id for preset in presets]
            count = f"{len(presets)} preset{'s' if len(presets) != 1 else ''}"
            description = f"{count} for [code]{target}[/]"
        if not args.yes and not confirm_ask(f"Delete {description}?"):
            console.print("\nExiting...")
            return
        for preset_id in preset_ids:
            store.delete(preset_id)
        console.print(f"Deleted {description}")


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
        help="Watch presets in realtime",
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
    presets: list[Preset],
    *,
    base: str | None,
    repo: str | None,
) -> list[Preset]:
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


def _apply_name(configuration: PresetConfiguration, name: str | None, *, required: bool) -> None:
    if name is not None:
        configuration.name = name
    if configuration.name is None:
        if required:
            raise CLIError(
                "The service name is required. Set `name` in the configuration or use --name"
            )
        return
    if not is_valid_dstack_resource_name(configuration.name):
        raise CLIError("The name must match '^[a-z][a-z0-9-]{1,40}$'")


def _resolve_session_ref(ref: str) -> str:
    """A session reference may be a preset id or a claimed name."""
    if (get_presets_dir() / ref).is_dir():
        return ref
    claims = find_session_name_claims(ref)
    if len(claims) == 1:
        return claims[0].preset_id
    return ref


def _confirm_preset_creation(store: PresetStore, name: str | None, *, assume_yes: bool) -> bool:
    """One apply-style confirmation; reassigns the name from any holder on yes."""
    preset_holder = None
    session_holders = []
    if name is not None:
        preset_holder = store.find_by_name(name)
        session_holders = [
            session
            for session in find_session_name_claims(name)
            if preset_holder is None or session.preset_id != preset_holder.id
        ]
    holders = []
    if preset_holder is not None:
        holders.append(f"preset [code]{preset_holder.id}[/]")
    holders.extend(f"preset [code]{session.preset_id}[/]" for session in session_holders)
    if holders:
        message = (
            f"The name [code]{name}[/] is already used by {', '.join(holders)}."
            f" Reassign it to a new preset?"
        )
    elif name is not None:
        message = f"Create the preset [code]{name}[/]?"
    else:
        message = "Create the preset?"
    if not assume_yes and not confirm_ask(message):
        return False
    if preset_holder is not None and name is not None:
        store.release_name(name)
    for session in session_holders:
        session.update_manifest(name=None)
    return True


def _get_effective_configuration(
    configuration: PresetConfiguration,
    args: argparse.Namespace,
    *,
    require_name: bool = True,
) -> PresetConfiguration:
    _apply_name(configuration, args.name, required=require_name)
    if getattr(args, "max_trials", None) is not None:
        configuration.max_trials = args.max_trials
    profile = load_profile_from_args(args=args, repo_dir=Path.cwd())
    for field in ProfileParams.__fields__:
        if getattr(configuration, field) is None:
            setattr(configuration, field, getattr(profile, field))
    apply_profile_args(args, configuration)
    return PresetConfiguration.parse_obj(configuration.dict())
