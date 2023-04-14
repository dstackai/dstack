import argparse
import os
from typing import List

from dstack.api.backend import list_backends
from dstack.backend.base import Backend
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.cli.config import config
from dstack.core.error import check_config, check_git
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
    def _command(self, args: argparse.Namespace):
        repo = RemoteRepo(repo_ref=config.repo_user_config.repo_ref, local_repo_dir=os.getcwd())
        backends = list_backends(repo)
        args.prune_action(args, backends)

    @staticmethod
    def prune_cache(args: argparse.Namespace, backends: List[Backend]):
        for backend in backends:
            backend.delete_workflow_cache(args.workflow)
            console.print(f"[gray58]Cache pruned (backend: {backend.name})[/]")
