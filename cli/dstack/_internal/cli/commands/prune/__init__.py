import argparse

from rich_argparse import RichHelpFormatter

from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client
from dstack._internal.cli.configuration import resolve_configuration_path
from dstack.api.hub import HubClient


class PruneCommand(BasicCommand):
    NAME = "prune"
    DESCRIPTION = "Prune cache"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser: argparse.ArgumentParser
        subparsers = self._parser.add_subparsers(title="entities", dest="entity", required=True)
        cache_cmd = subparsers.add_parser(
            "cache", help="Configuration cache", formatter_class=RichHelpFormatter
        )
        add_project_argument(cache_cmd)
        cache_cmd.add_argument(
            "working_dir",
            metavar="WORKING_DIR",
            type=str,
            help="The working directory of the run",
        )
        cache_cmd.add_argument(
            "-f",
            "--file",
            metavar="FILE",
            help="The path to the run configuration file. Defaults to WORKING_DIR/.dstack.yml.",
            type=str,
            dest="file_name",
        )
        cache_cmd.set_defaults(prune_action=self.prune_cache)

    @check_init
    def _command(self, args: argparse.Namespace):
        hub_client = get_hub_client(project_name=args.project)
        args.prune_action(args, hub_client)

    @staticmethod
    def prune_cache(args: argparse.Namespace, hub_client: HubClient):
        configuration_path = str(resolve_configuration_path(args.file_name, args.working_dir))
        hub_client.delete_configuration_cache(configuration_path=configuration_path)
        console.print(f"[grey58]Cache pruned[/]")
