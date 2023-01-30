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


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


class ArtifactCommand(BasicCommand):
    NAME = 'artifacts'
    DESCRIPTION = 'List or download artifacts'

    def __init__(self, parser):
        super(ArtifactCommand, self).__init__(parser)

    def register(self):
        subparsers = self._parser.add_subparsers()

        list_parser = subparsers.add_parser("list", help="List artifacts", )
        list_parser.add_argument("run_name_or_tag_name", metavar="RUN | :TAG", type=str,
                                 help="A name of a run or a tag")
        list_parser.set_defaults(func=self.list)

        download_parser = subparsers.add_parser("download", help="Download artifacts", )
        download_parser.add_argument("run_name_or_tag_name", metavar="(RUN | :TAG)", type=str,
                                     help="A name of a run or a tag")
        download_parser.add_argument("-o", "--output", help="The directory to download artifacts to. "
                                                            "By default, it's the current directory.", type=str)
        download_parser.set_defaults(func=self.download)

    @check_config
    @check_git
    def _command(self, args: Namespace):
        self.list(args)

    @check_config
    @check_git
    def list(self, args: Namespace):
        repo_data = load_repo_data()
        console = Console()
        table = Table(box=None)
        table.add_column("ARTIFACT", style="bold", no_wrap=True)
        table.add_column("FILE")
        table.add_column("SIZE", style="dark_sea_green4")
        table.add_column("BACKEND", style="bold")
        anyone = False
        for backend in list_backends():
            run_name = _run_name(repo_data, backend, args)
            if run_name is None:
                continue
            anyone = True
            run_artifact_files = backend.list_run_artifact_files(repo_data, run_name)
            previous_artifact_name = None
            for (artifact_name, file_name, file_size) in run_artifact_files:
                table.add_row(artifact_name if previous_artifact_name != artifact_name else "",
                              file_name, sizeof_fmt(file_size), backend.name)
                previous_artifact_name = artifact_name
        if anyone:
            console.print(table)
        else:
            sys.exit(f"Nothing found '{args.run_name_or_tag_name}'")

    @check_config
    @check_git
    def download(self, args: Namespace):
        repo_data = load_repo_data()
        for backend in list_backends():
            run_name = _run_name(repo_data, backend, args)
            backend.download_run_artifact_files(repo_data, run_name, args.output)
