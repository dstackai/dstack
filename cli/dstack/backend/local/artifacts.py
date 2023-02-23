from pathlib import Path

from dstack.core.repo import RepoAddress


def get_artifacts_path(dstack_dir: Path, repo_address: RepoAddress) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_address.path())
