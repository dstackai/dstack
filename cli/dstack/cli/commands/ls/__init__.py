from argparse import Namespace

from rich.table import Table

from dstack.api.artifacts import list_artifacts_with_merged_backends
from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.core.error import check_config, check_git
from dstack.utils.common import sizeof_fmt


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
        run_names = []
        backends_run_name = []
        for backend in backends:
            try:
                run_name, _ = get_tagged_run_name(repo_data, backend, args.run_name_or_tag_name)
                run_names.append(run_name)
                backends_run_name.append(backend)
            except (TagNotFoundError, RunNotFoundError):
                pass

        if len(run_names) == 0:
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        artifacts = list_artifacts_with_merged_backends(
            backends_run_name, load_repo_data(), run_names[0]
        )
        for artifact, backends in artifacts:
            for i, file in enumerate(artifact.files):
                table.add_row(
                    artifact.name if i == 0 else "",
                    file.filepath,
                    sizeof_fmt(file.filesize_in_bytes),
                    ", ".join(b.name for b in backends),
                )
        console.print(table)
