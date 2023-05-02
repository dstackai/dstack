import os
import shutil
import sys
from argparse import Namespace
from pathlib import Path

from dstack.api.hub import HubClient
from dstack.api.runs import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.cli.commands import BasicCommand
from dstack.cli.common import add_project_argument, check_init, console
from dstack.cli.config import get_hub_client
from dstack.utils.common import get_dstack_dir


class CpCommand(BasicCommand):
    NAME = "cp"
    DESCRIPTION = "Copy artifact files to a local target path"

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
            run_name, _ = get_tagged_run_name(hub_client, args.run_name_or_tag_name)
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
    tmp_output_dir = get_dstack_dir() / "tmp" / "copied_artifacts" / hub_client.repo.repo_id
    tmp_output_dir.mkdir(parents=True, exist_ok=True)
    source = _normalize_source(source)
    hub_client.download_run_artifact_files(
        run_name=run_name,
        output_dir=tmp_output_dir,
        files_path=source,
    )
    tmp_job_output_dir = None
    # TODO: We support copy for a single job.
    # Decide later how to work with multi-job artifacts.
    for job_dir in os.listdir(tmp_output_dir):
        if job_dir.startswith(run_name):
            tmp_job_output_dir = tmp_output_dir / job_dir
            break
    if tmp_job_output_dir is None:
        console.print(f"Artifact source path '{source}' does not exist")
        exit(1)
    source_full_path = tmp_job_output_dir / source
    target_path = Path(target)
    if source_full_path.is_dir():
        if target_path.exists() and not target_path.is_dir():
            console.print(f"Local target path '{target}' exists and is not a directory")
            shutil.rmtree(tmp_job_output_dir)
            exit(1)
        if sys.version_info[1] >= 8:
            shutil.copytree(source_full_path, target, dirs_exist_ok=True)
        else:  # todo: drop along with 3.7
            import distutils.dir_util

            distutils.dir_util.copy_tree(source_full_path, target)
    else:
        if not target_path.exists():
            if target.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_full_path, target_path)
    shutil.rmtree(tmp_job_output_dir)


def _normalize_source(source: str) -> str:
    source = str(Path(source))
    if source.startswith("/"):
        source = source[1:]
    return source
