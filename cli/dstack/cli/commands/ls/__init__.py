from argparse import Namespace
from collections import defaultdict
from pathlib import Path
from typing import Optional

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

        for artifact, _ in artifacts:
            artifact.files = sorted(
                [
                    f
                    for f in artifact.files
                    if str(Path(artifact.name, f.filepath)).startswith(args.prefix)
                ],
                key=lambda f: f.filepath,
            )

        if args.recursive:
            for artifact, backends in artifacts:
                for i, file in enumerate(artifact.files):
                    table.add_row(
                        artifact.name if i == 0 else "",
                        file.filepath,
                        sizeof_fmt(file.filesize_in_bytes),
                        ", ".join(b.name for b in backends),
                    )
        else:
            entries = {}
            for artifact, backends in artifacts:
                if entries.get(artifact.name) is None:
                    entries[artifact.name] = {}
                for i, file in enumerate(artifact.files):
                    entry_name = _get_entry_name(file.filepath, args.prefix)
                    if entries[artifact.name].get(entry_name) is None:
                        entries[artifact.name][entry_name] = {"size": 0, "backends": set()}
                    entries[artifact.name][entry_name]["size"] += file.filesize_in_bytes
                    entries[artifact.name][entry_name]["backends"].update(backends)

            for artifact_name, entry_map in entries.items():
                first_entry = True
                for entry_name, entry_dict in entry_map.items():
                    table.add_row(
                        artifact_name if first_entry else "",
                        entry_name,
                        sizeof_fmt(entry_dict["size"])
                        if not entry_name.endswith("/") or args.total
                        else "",
                        ", ".join(b.name for b in entry_dict["backends"]),
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
