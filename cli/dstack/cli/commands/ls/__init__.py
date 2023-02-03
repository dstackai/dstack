import sys

from argparse import Namespace
from rich.table import Table

from dstack.core.error import check_config, check_git
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.api.artifacts import list_artifacts_with_merged_backends
from dstack.api.repo import load_repo_data
from dstack.api.backend import list_backends


def _run_name(repo_data, backend, args):
    if args.run_name_or_tag_name.startswith(":"):
        tag_name = args.run_name_or_tag_name[1:]
        tag_head = backend.get_tag_head(repo_data, tag_name)
        if tag_head:
            return tag_head.run_name
    else:
        run_name = args.run_name_or_tag_name
        job_heads = backend.list_job_heads(repo_data, run_name)
        if job_heads:
            return run_name


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


class LsCommand(BasicCommand):
    NAME = "ls"
    DESCRIPTION = "List artifacts"

    def __init__(self, parser):
        super(LsCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="RUN | :TAG",
            type=str,
            help="A name of a run or a tag",
        )

    @check_config
    @check_git
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("ARTIFACT", style="bold", no_wrap=True)
        table.add_column("FILE")
        table.add_column("SIZE", style="dark_sea_green4")
        table.add_column("BACKENDS", style="bold")

        repo_data = load_repo_data()
        backends = list_backends()
        run_names = [_run_name(repo_data, b, args) for b in backends]
        run_names = [r for r in run_names if r is not None]

        if len(run_names) == 0:
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        artifacts = list_artifacts_with_merged_backends(backends, load_repo_data(), run_names[0])
        previous_artifact_name = None
        for artifact, backends in artifacts:
            table.add_row(
                artifact.name if previous_artifact_name != artifact.name else "",
                artifact.file,
                sizeof_fmt(artifact.filesize_in_bytes),
                ", ".join(b.name for b in backends),
            )
            previous_artifact_name = artifact.name

        console.print(table)
