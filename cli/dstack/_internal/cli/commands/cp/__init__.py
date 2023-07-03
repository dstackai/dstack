from argparse import Namespace

from dstack._internal.api.artifacts import download_artifact_files_hub
from dstack._internal.api.runs import RunNotFoundError, TagNotFoundError, get_tagged_run_name_hub
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.common import add_project_argument, check_init, console
from dstack._internal.cli.config import get_hub_client
from dstack._internal.core.error import DstackError
from dstack.api.hub import HubClient


class CpCommand(BasicCommand):
    NAME = "cp"
    DESCRIPTION = "Copy artifact files"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        add_project_argument(self._parser)
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="(RUN | :TAG)",
            type=str,
            help="The name of the run or the tag",
        )
        self._parser.add_argument(
            "source",
            metavar="SOURCE",
            type=str,
            help="A path of an artifact file or directory",
        )
        self._parser.add_argument(
            "target",
            metavar="TARGET",
            type=str,
            help="A local path to download artifact file or directory into",
        )

    @check_init
    def _command(self, args: Namespace):
        hub_client = get_hub_client(project_name=args.project)
        try:
            run_name, _ = get_tagged_run_name_hub(hub_client, args.run_name_or_tag_name)
        except (TagNotFoundError, RunNotFoundError):
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)
        _copy_artifact_files(
            hub_client=hub_client,
            run_name=run_name,
            source=args.source,
            target=args.target,
        )
        console.print("Artifact files copied")


def _copy_artifact_files(hub_client: HubClient, run_name: str, source: str, target: str):
    try:
        download_artifact_files_hub(hub_client, run_name, source, target)
    except DstackError as e:
        console.print(e.message)
        exit(1)
