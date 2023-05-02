import argparse

from rich_argparse import RichHelpFormatter

from dstack.api.hub import HubClient
from dstack.cli.commands import BasicCommand
from dstack.cli.common import add_project_argument, check_init, console
from dstack.cli.config import get_hub_client


class PruneCommand(BasicCommand):
    NAME = "prune"
    DESCRIPTION = "Prunes cache from the storage"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser: argparse.ArgumentParser
        subparsers = self._parser.add_subparsers(title="entities", dest="entity", required=True)
        cache_cmd = subparsers.add_parser(
            "cache", help="Workflow cache", formatter_class=RichHelpFormatter
        )
        add_project_argument(cache_cmd)
        cache_cmd.add_argument(
            "workflow",
            metavar="WORKFLOW",
            help="A workflow name to prune cache",
        )
        cache_cmd.set_defaults(prune_action=self.prune_cache)

    @check_init
    def _command(self, args: argparse.Namespace):
        hub_client = get_hub_client(project_name=args.project)
        args.prune_action(args, hub_client)

    @staticmethod
    def prune_cache(args: argparse.Namespace, hub_client: HubClient):
        hub_client.delete_workflow_cache(args.workflow)
        console.print(f"[gray58]Cache pruned[/]")
