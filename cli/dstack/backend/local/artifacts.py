import os
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from dstack.backend.local.storage import _list_all_objects
from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress


def get_artifacts_path(dstack_dir: Path, repo_address: RepoAddress) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_address.path())


def list_run_artifact_files(
    path: str, repo_address: RepoAddress, run_name: str
) -> Generator[Artifact, None, None]:
    root = Path.joinpath(path, "artifacts", repo_address.path())
    artifact_prefix = f"{run_name},"
    list_iterator = _list_all_objects(Root=root, Prefix=artifact_prefix)
    for job_id, path, file_size in list_iterator:
        artifact, file = path.split("/", maxsplit=1)
        if file_size > 0:
            yield Artifact(job_id=job_id, name=artifact, file=file, filesize_in_bytes=file_size)


def upload_job_artifact_files(
    path: str,
    repo_address: RepoAddress,
    job_id: str,
    artifact_name: str,
    local_path: Path,
):
    pass
