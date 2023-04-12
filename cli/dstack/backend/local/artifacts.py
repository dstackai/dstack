from pathlib import Path


def get_artifacts_path(dstack_dir: Path, repo_id: str) -> Path:
    return Path.joinpath(dstack_dir, "artifacts", repo_id)
