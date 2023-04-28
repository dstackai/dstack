from argparse import Namespace
from pathlib import Path

from rich.table import Table

from dstack.api.runs import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import check_backend, check_config, check_git, check_init, console
from dstack.cli.config import get_hub_client
from dstack.utils.common import sizeof_fmt


class LsCommand(BasicCommand):
    NAME = "ls"
    DESCRIPTION = "List artifacts"

    def __init__(self, parser):
        super(LsCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument(
            "--project",
            type=str,
            help="Hub project to execute the command",
            default=None,
        )
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="RUN | :TAG",
            type=str,
            help="A name of a run or a tag",
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
        self._parser.add_argument(
            "-t", "--total", help="Show total folder size", action="store_true"
        )

    @check_config
    @check_git
    @check_backend
    @check_init
    def _command(self, args: Namespace):
        table = Table(box=None)
        table.add_column("ARTIFACT", style="bold", no_wrap=True)
        table.add_column("FILE")
        table.add_column("SIZE", style="dark_sea_green4")

        hub_client = get_hub_client(project_name=args.project)
        try:
            run_name, _ = get_tagged_run_name(hub_client, args.run_name_or_tag_name)
        except (TagNotFoundError, RunNotFoundError):
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        artifacts = hub_client.list_run_artifact_files(run_name)
        for artifact in artifacts:
            artifact.files = sorted(
                [
                    f
                    for f in artifact.files
                    if str(Path(artifact.name, f.filepath)).startswith(args.prefix)
                ],
                key=lambda f: f.filepath,
            )

        if args.recursive:
            for artifact in artifacts:
                for i, file in enumerate(artifact.files):
                    table.add_row(
                        artifact.name if i == 0 else "",
                        file.filepath,
                        sizeof_fmt(file.filesize_in_bytes),
                    )
        else:
            entries = {}
            for artifact in artifacts:
                if entries.get(artifact.name) is None:
                    entries[artifact.name] = {}
                for i, file in enumerate(artifact.files):
                    entry_name = _get_entry_name(file.filepath, args.prefix)
                    if entries[artifact.name].get(entry_name) is None:
                        entries[artifact.name][entry_name] = {"size": 0, "backends": set()}
                    entries[artifact.name][entry_name]["size"] += file.filesize_in_bytes

            for artifact_name, entry_map in entries.items():
                first_entry = True
                for entry_name, entry_dict in entry_map.items():
                    table.add_row(
                        artifact_name if first_entry else "",
                        entry_name,
                        sizeof_fmt(entry_dict["size"])
                        if not entry_name.endswith("/") or args.total
                        else "",
                    )
                    first_entry = False
        console.print(table)


def _get_entry_name(filepath: str, prefix: str) -> str:
    if prefix == "":
        prefix_parts_num = 1
    else:
        prefix_parts_num = len(Path(prefix).parts)

    path_parts = Path(filepath).parts
    entry_name = str(Path(*path_parts[:prefix_parts_num]))
    if len(path_parts) > prefix_parts_num:
        entry_name += "/"
    return entry_name
