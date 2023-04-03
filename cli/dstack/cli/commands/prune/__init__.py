import argparse
from typing import List

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.backend.base import Backend
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.core.error import check_config, check_git
from dstack.core.repo import LocalRepoData


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
    def _command(self, args: argparse.Namespace):
        repo_data = load_repo_data()
        backends = list_backends()
        args.prune_action(args, backends, repo_data)

    @staticmethod
    def prune_cache(args: argparse.Namespace, backends: List[Backend], repo_data: LocalRepoData):
        for backend in backends:
            backend.delete_workflow_cache(
                repo_data, repo_data.local_repo_user_email or "default", args.workflow
            )
            console.print(f"[gray58]Cache pruned (backend: {backend.name})[/]")
