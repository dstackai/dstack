from argparse import Namespace

from rich.table import Table

from dstack._internal.api.runs import RunNotFoundError, TagNotFoundError, get_tagged_run_name_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client
from dstack._internal.utils.common import sizeof_fmt


class LsCommand(BasicCommand):
    NAME = "ls"
    DESCRIPTION = "List artifacts"

    def __init__(self, parser):
        super(LsCommand, self).__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="RUN | :TAG",
            type=str,
            help="The name of the run or the tag",
        )
        self._parser.add_argument(
            "prefix",
            metavar="SEARCH_PREFIX",
            type=str,
            help="Show files starting with prefix",
            nargs="?",
            default="",
        )

        self._parser.add_argument(
            "-r", "--recursive", help="Show all files recursively", action="store_true"
        )

    @check_init
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("ARTIFACT", style="bold", no_wrap=True)
        table.add_column("FILE")
        table.add_column("SIZE", style="dark_sea_green4")

        hub_client = get_hub_client(project_name=args.project)
        try:
            run_name, _ = get_tagged_run_name_hub(hub_client, args.run_name_or_tag_name)
        except (TagNotFoundError, RunNotFoundError):
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        artifacts = hub_client.list_run_artifact_files(
            run_name, prefix=args.prefix, recursive=args.recursive
        )
        artifact = sorted(artifacts, key=lambda a: a.path)
        for artifact in artifacts:
            files = sorted(artifact.files, key=lambda f: f.filepath)
            for i, file in enumerate(files):
                table.add_row(
                    artifact.name if i == 0 else "",
                    file.filepath,
                    sizeof_fmt(file.filesize_in_bytes)
                    if file.filesize_in_bytes is not None
                    else "",
                )
        console.print(table)
