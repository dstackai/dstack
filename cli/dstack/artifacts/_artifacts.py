from typing import Optional

from dstack._internal.api import workflow_api
from dstack._internal.api.artifacts import download_backend_artifact_files


def download(run_name: str, artifact_path: str, target_path: Optional[str] = None):
    if target_path is None:
        target_path = artifact_path
    backend = workflow_api.get_current_backend()
    repo_id = workflow_api.get_current_repo_id()
    download_backend_artifact_files(
        backend=backend,
        repo_id=repo_id,
        run_name=run_name,
        source=artifact_path,
        target=target_path,
    )
