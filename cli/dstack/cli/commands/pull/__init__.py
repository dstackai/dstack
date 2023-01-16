import sys

from argparse import Namespace
from rich.console import Console
from rich.table import Table

from dstack.core.error import check_config, check_git
from dstack.cli.commands import BasicCommand
from dstack.api.repo import load_repo_data
from dstack.api.backend import list_backends


def _run_name(repo_data, backend, args):
    if args.run_name_or_tag_name.startswith(":"):
        tag_name = args.run_name_or_tag_name[1:]
        tag_head = backend.get_tag_head(repo_data, tag_name)
        if tag_head:
            return tag_head.run_name
        else:
            sys.exit(f"Cannot find the tag '{tag_name}'")
    else:
        run_name = args.run_name_or_tag_name
        job_heads = backend.list_job_heads(repo_data, run_name)
        if job_heads:
            return run_name
        else:
            sys.exit(f"Cannot find the run '{run_name}'")


class PullCommand(BasicCommand):
    NAME = 'pull'
    DESCRIPTION = 'Download artifacts'

    def __init__(self, parser):
        super(PullCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument("run_name_or_tag_name", metavar="(RUN | :TAG)", type=str,
                                     help="A name of a run or a tag")
        self._parser.add_argument("-o", "--output", help="The directory to download artifacts to. "
                                                            "By default, it's the current directory.", type=str)

    @check_config
    @check_git
    def _command(self, args: Namespace):
        repo_data = load_repo_data()
        for backend in list_backends():
            run_name = _run_name(repo_data, backend, args)
            backend.download_run_artifact_files(repo_data, run_name, args.output)
