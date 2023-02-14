from pathlib import Path

from dstack.core.artifact import Artifact
from dstack.core.repo import RepoAddress


def get_artifacts_path(dstack_dir: Path, repo_address: RepoAddress) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_address.path())


def upload_job_artifact_files(
    path: str,
    repo_address: RepoAddress,
    job_id: str,
    artifact_name: str,
    local_path: Path,
):
    pass
