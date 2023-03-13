import os
import shutil
from argparse import Namespace
from pathlib import Path

from dstack.api.backend import list_backends
from dstack.api.repo import load_repo_data
from dstack.api.run import RunNotFoundError, TagNotFoundError, get_tagged_run_name
from dstack.backend.base import Backend
from dstack.cli.commands import BasicCommand
from dstack.cli.common import console
from dstack.core.config import get_dstack_dir
from dstack.core.error import BackendError, check_config, check_git
from dstack.core.repo import RepoAddress


class CpCommand(BasicCommand):
    NAME = "cp"
    DESCRIPTION = "Copy artifact files to a local target path"

    def __init__(self, parser):
        super().__init__(parser)

    def register(self):
        self._parser.add_argument(
            "run_name_or_tag_name",
            metavar="(RUN | :TAG)",
            type=str,
            help="A name of a run or a tag",
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

    @check_config
    @check_git
    def _command(self, args: Namespace):
        repo_data = load_repo_data()
        backends = list_backends()
        run_name = None
        backend = None
        for backend in backends:
            try:
                run_name, _ = get_tagged_run_name(repo_data, backend, args.run_name_or_tag_name)
                break
            except (TagNotFoundError, RunNotFoundError):
                pass

        if run_name is None:
            console.print(f"Cannot find the run or tag '{args.run_name_or_tag_name}'")
            exit(1)

        _copy_artifact_files(
            backend=backend,
            repo_address=repo_data,
            run_name=run_name,
            source=args.source,
            target=args.target,
        )
        console.print("Artifact files copied")


def _copy_artifact_files(
    backend: Backend, repo_address: RepoAddress, run_name: str, source: str, target: str
):
    tmp_output_dir = get_dstack_dir() / "tmp" / "copied_artifacts" / repo_address.path()
    tmp_output_dir.mkdir(parents=True, exist_ok=True)
    source = _normalize_source(source)
    backend.download_run_artifact_files(
        repo_address=repo_address,
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
        shutil.copytree(source_full_path, target, dirs_exist_ok=True)
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
