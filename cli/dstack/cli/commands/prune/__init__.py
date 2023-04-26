import argparse
import os

from dstack.api.hub import HubClient
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config
from dstack.core.repo import RemoteRepo


class PruneCommand(BasicCommand):
    NAME = "prune"
    DESCRIPTION = "Prunes cache from the storage"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser: argparse.ArgumentParser
        subparsers = self._parser.add_subparsers(title="entities", dest="entity", required=True)

        cache_cmd = subparsers.add_parser("cache", help="Workflow cache")
        cache_cmd.add_argument(
            "workflow", metavar="WORKFLOW", help="A workflow name to prune cache"
        )
        cache_cmd.set_defaults(prune_action=self.prune_cache)

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: argparse.Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        hub_client = HubClient(repo=repo)
        args.prune_action(args, hub_client)

    @staticmethod
    def prune_cache(args: argparse.Namespace, hub_client: HubClient):
        hub_client.delete_workflow_cache(args.workflow)
        console.print(f"[gray58]Cache pruned[/]")
