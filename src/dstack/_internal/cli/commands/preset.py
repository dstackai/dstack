import argparse
import io
import os
import sys
import time
from contextlib import redirect_stderr, suppress
from pathlib import Path
from typing import Optional

from argcomplete import FilesCompleter  # type: ignore[attr-defined]
from rich.live import Live

from dstack._internal.cli.commands import BaseCommand
from dstack._internal.cli.models.presets import (
    Preset,
    PresetListOutput,
)
from dstack._internal.cli.services.completion import ProjectNameCompleter
from dstack._internal.cli.services.configurators import APPLY_STDIN_NAME
from dstack._internal.cli.services.configurators.preset import (
    PresetConfigurator,
    register_creation_args,
)
from dstack._internal.cli.services.presets.create import (
    CreationStopped,
    create_preset,
    load_session_configuration,
    reconcile_detached_sessions,
    show_preset_session_logs,
    stop_preset_session,
)
from dstack._internal.cli.services.presets.export import export_preset
from dstack._internal.cli.services.presets.output import get_presets_table, print_presets
from dstack._internal.cli.services.presets.session import (
    list_preset_sessions,
    load_preset_session,
    load_resumable_session,
    resolve_session_ref,
)
from dstack._internal.cli.services.presets.store import (
    PresetStore,
    load_preset_configuration,
    parse_preset_configuration,
)
from dstack._internal.cli.services.profile import (
    register_profile_args,
)
from dstack._internal.cli.utils.common import (
    LIVE_TABLE_PROVISION_INTERVAL_SECS,
    LIVE_TABLE_REFRESH_RATE_PER_SEC,
    confirm_ask,
    console,
    warn,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.presets import PresetConfiguration
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
        register_creation_args(create_parser)
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

        resume_parser = preset_subparsers.add_parser(
            "resume",
            help="Resume an interrupted preset creation",
            formatter_class=self._parser.formatter_class,
        )
        resume_parser.add_argument("preset", metavar="ID", help="The preset ID or name")
        resume_parser.add_argument(
            "--keep-service",
            action="store_true",
            help="Leave the verified service running",
        )
        resume_parser.set_defaults(subfunc=self._resume)

        export_parser = preset_subparsers.add_parser(
            "export",
            help="Export a preset as a service configuration",
            formatter_class=self._parser.formatter_class,
        )
        export_parser.add_argument("preset", metavar="ID", help="The preset ID or name")
        export_parser.add_argument(
            "-f",
            "--file",
            required=True,
            metavar="FILE",
            dest="destination",
            help="The service configuration file to write",
        )
        export_parser.add_argument("--force", action="store_true", help="Overwrite existing files")
        export_parser.set_defaults(subfunc=self._export)

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
            print(PresetListOutput(presets=presets).model_dump_json())
            return
        verbose = args.verbose
        if not getattr(args, "watch", False):
            presets, sessions = self._list_presets_and_sessions(base=base, repo=repo)
            print_presets(
                presets,
                sessions=sessions,
                verbose=verbose,
                all_presets=args.all_presets,
                limit=args.limit,
            )
            return
        # The store warns about unreadable presets on stderr once per read;
        # inside Live that would tear the render on every refresh. The first
        # read happens before Live starts so warnings print once, above the
        # table; refreshes read with stderr suppressed.
        presets, sessions = self._list_presets_and_sessions(base=base, repo=repo)
        with Live(console=console, refresh_per_second=LIVE_TABLE_REFRESH_RATE_PER_SEC) as live:
            while True:
                live.update(
                    get_presets_table(
                        presets,
                        sessions=sessions,
                        verbose=verbose,
                        all_presets=args.all_presets,
                        limit=args.limit,
                    )
                )
                time.sleep(LIVE_TABLE_PROVISION_INTERVAL_SECS)
                with redirect_stderr(io.StringIO()):
                    presets, sessions = self._list_presets_and_sessions(base=base, repo=repo)

    def _list_presets_and_sessions(
        self, *, base: str | None, repo: str | None
    ) -> tuple[list[Preset], list[dict]]:
        self._reconcile()
        presets = PresetStore().list()
        sessions = list_preset_sessions()
        if base or repo:
            repo_to_base = {preset.model: preset.base for preset in presets}
            presets = _filter_presets(presets, base=base, repo=repo)
            sessions = [
                session
                for session in sessions
                if _session_matches_model(session, base=base, repo=repo, repo_to_base=repo_to_base)
            ]
        return presets, sessions

    def _create(self, args: argparse.Namespace) -> None:
        warn(
            "`dstack preset create` is deprecated; use `dstack apply -f <configuration>`",
            stderr=True,
        )
        _check_stdin_configuration_confirmable(args)
        _, configuration = _read_configuration_arg(args.configuration_file)
        # A thin adapter over the configurator, the same path `dstack apply` takes.
        # The create parser has no -d, which the configurator contract reads.
        args.detach = False
        configurator = PresetConfigurator(api_client=Client.from_config(project_name=args.project))
        configurator.apply_configuration(
            conf=configuration,
            configuration_path=args.configuration_file,
            command_args=args,
            configurator_args=args,
        )

    def _resume(self, args: argparse.Namespace) -> None:
        session = load_resumable_session(resolve_session_ref(args.preset))
        try:
            result = create_preset(
                api=Client.from_config(project_name=args.project),
                configuration=load_session_configuration(session),
                store=PresetStore(),
                keep_service=args.keep_service,
                resume_session=session,
                user_prompt=session.read_prompt(),
            )
        except KeyboardInterrupt:
            return  # the interrupt handler already reported detach / stop
        except CreationStopped:
            return  # stopped from another CLI, which reported the interruption
        if args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _logs(self, args: argparse.Namespace) -> None:
        try:
            result = show_preset_session_logs(
                project=args.project,
                store=PresetStore(),
                preset_id=resolve_session_ref(args.preset),
                follow=args.follow,
                keep_service=args.keep_service,
            )
        except KeyboardInterrupt:
            return  # a log viewer: Ctrl+C just stops watching, quietly
        except CreationStopped:
            return  # stopped from another CLI, which reported the interruption
        if result is not None and args.keep_service:
            console.print(f"Final service [code]{result.final_run_name}[/] kept running")

    def _stop(self, args: argparse.Namespace) -> None:
        preset_id = resolve_session_ref(args.preset)
        if not args.yes and not confirm_ask(f"Stop creating preset [code]{preset_id}[/]?"):
            console.print("\nExiting...")
            return
        stop_preset_session(Client.from_config(project_name=args.project), preset_id)

    def _get(self, args: argparse.Namespace) -> None:
        self._reconcile()
        preset = PresetStore().find_by_id_or_name(args.preset)
        if preset is None:
            preset = _get_unfinished_preset(args.preset)
        if preset is None:
            raise CLIError(f"Preset {args.preset!r} does not exist")
        print(preset.model_dump_json())

    def _export(self, args: argparse.Namespace) -> None:
        store = PresetStore()
        preset = store.find_by_id_or_name(args.preset)
        if preset is None:
            raise CLIError(f"Preset {args.preset!r} does not exist")
        written = export_preset(
            preset,
            preset_dir=store.root / preset.id,
            destination=Path(args.destination),
            force=args.force,
        )
        console.print(
            f"Preset [code]{preset.id}[/] exported to [code]{args.destination}[/]"
            f" ({len(written)} files). Deploy it with"
            f" [code]dstack apply -f {args.destination}[/]"
        )

    def _delete(self, args: argparse.Namespace) -> None:
        store = PresetStore()
        if args.preset is not None:
            try:
                preset = store.find_by_id_or_name(args.preset)
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


def _get_unfinished_preset(ref: str) -> Optional[Preset]:
    """The preset as its creation session knows it, for any state but verified."""
    try:
        session = load_preset_session(resolve_session_ref(ref))
    except CLIError:
        return None
    state = session.read_state()
    if state is None or state.status == "success":
        return None
    return Preset(
        status=state.status,
        id=state.id,
        name=state.name,
        configuration=load_session_configuration(session),
        submitted_at=state.created_at,
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
        help="The preset name",
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
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        dest="all_presets",
        help="Show all presets. By default, it only shows unfinished creations or the last one.",
    )
    parser.add_argument(
        "-n",
        "--last",
        metavar="COUNT",
        type=int,
        dest="limit",
        help="Show only the last N presets. Implies --all",
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


def _read_configuration_arg(configuration_file: str) -> tuple[str, PresetConfiguration]:
    """`-f <path>`, or `-f -` for stdin — the same convention as `dstack apply`."""
    if configuration_file == APPLY_STDIN_NAME:
        return APPLY_STDIN_NAME, parse_preset_configuration(sys.stdin)
    path = Path(configuration_file)
    return str(path.resolve()), load_preset_configuration(path)


def _check_stdin_configuration_confirmable(args: argparse.Namespace) -> None:
    # Same rule as `dstack apply`: the confirmation prompt cannot read from a
    # stdin that is the configuration itself.
    if not args.yes and args.configuration_file == APPLY_STDIN_NAME:
        raise CLIError("Cannot read configuration from stdin if -y/--yes is not specified")
