import argparse
from typing import List

from dstack.api.backend import list_backends
from dstack.api.repos import load_repo
from dstack.backend.base import Backend
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import config


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
        repo = load_repo(config.repo_user_config)
        backends = list_backends(repo)
        args.prune_action(args, backends)

    @staticmethod
    def prune_cache(args: argparse.Namespace, backends: List[Backend]):
        for backend in backends:
            backend.delete_workflow_cache(args.workflow)
            console.print(f"[gray58]Cache pruned (backend: {backend.name})[/]")
