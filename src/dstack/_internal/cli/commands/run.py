import argparse
from uuid import UUID

from dstack._internal.cli.commands import APIBaseCommand
from dstack._internal.cli.services.completion import RunNameCompleter
from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import CLIError, ResourceNotExistsError
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class RunCommand(APIBaseCommand):
    NAME = "run"
    DESCRIPTION = "Manage runs"

    def _register(self):
        super()._register()
        subparsers = self._parser.add_subparsers(dest="action")

        # TODO: Add `list` subcommand and make `dstack ps` an alias to `dstack run list`

        get_parser = subparsers.add_parser(
            "get", help="Get a run", formatter_class=self._parser.formatter_class
        )
        name_group = get_parser.add_mutually_exclusive_group(required=True)
        name_group.add_argument(
            "name",
            nargs="?",
            metavar="NAME",
            help="The name of the run",
        ).completer = RunNameCompleter()  # type: ignore[attr-defined]
        name_group.add_argument(
            "--id",
            type=str,
            help="The ID of the run (UUID)",
        )
        get_parser.add_argument(
            "--json",
            action="store_true",
            required=True,
            help="Output in JSON format",
        )
        get_parser.set_defaults(subfunc=self._get)

    def _command(self, args: argparse.Namespace):
        super()._command(args)
        if hasattr(args, "subfunc"):
            args.subfunc(args)
        else:
            self._parser.print_help()

    def _get(self, args: argparse.Namespace):
        # TODO: Implement non-json output format
        run_id = None
        if args.id is not None:
            try:
                run_id = UUID(args.id)
            except ValueError:
                raise CLIError(f"Invalid UUID format: {args.id}")

        try:
            if args.id is not None:
                run = self.api.client.runs.get(project_name=self.api.project, run_id=run_id)
            else:
                run = self.api.client.runs.get(project_name=self.api.project, run_name=args.name)
        except ResourceNotExistsError:
            console.print(f"Run [code]{args.name or args.id}[/] not found")
            exit(1)

        print(pydantic_orjson_dumps_with_indent(run.dict(), default=None))
