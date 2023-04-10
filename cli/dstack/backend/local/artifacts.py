from pathlib import Path


def get_artifacts_path(dstack_dir: Path, repo_name: str) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_name)
