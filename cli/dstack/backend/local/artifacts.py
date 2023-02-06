import os
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from dstack.backend.local.common import (
    delete_object,
    get_object,
    list_all_objects,
    list_objects,
    put_object,
)
from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress


def get_artifacts_path(dstack_dir: Path, repo_address: RepoAddress) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_address.path())


def list_run_artifact_files(
    path: str, repo_address: RepoAddress, run_name: str
) -> Generator[Artifact, None, None]:
    root = Path.joinpath(path, "artifacts", repo_address.path())
    artifact_prefix = f"{run_name},"
    list_iterator = list_all_objects(Root=root, Prefix=artifact_prefix)
    for job_id, path, file_size in list_iterator:
        artifact, file = path.split("/", maxsplit=1)
        if file_size > 0:
            yield Artifact(job_id, artifact, file, file_size)


def __remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


def upload_job_artifact_files(
    path: str,
    repo_address: RepoAddress,
    job_id: str,
    artifact_name: str,
    local_path: Path,
):
    pass


def list_run_artifact_files_and_folders(
    path_backend_dir: str, repo_address: RepoAddress, job_id: str, path: str
) -> List[Tuple[str, bool]]:
    pass
