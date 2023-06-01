from typing import Optional

from dstack._internal.api import workflow_api
from dstack._internal.api.artifacts import (
    download_backend_artifact_files,
    upload_backend_artifact_files,
)


def download(run_name: str, artifact_path: str, local_path: Optional[str] = None):
    if local_path is None:
        local_path = artifact_path
    backend = workflow_api.get_current_backend()
    repo_id = workflow_api.get_current_repo_id()
    download_backend_artifact_files(
        backend=backend,
        repo_id=repo_id,
        run_name=run_name,
        source=artifact_path,
        target=local_path,
    )


def upload(local_path: str, artifact_path: Optional[str] = None, tag: Optional[str] = None):
    if artifact_path is None:
        artifact_path = local_path
    backend = workflow_api.get_current_backend()
    repo_id = workflow_api.get_current_repo_id()
    job_id = workflow_api.get_current_job_id()
    upload_backend_artifact_files(
        backend=backend,
        repo_id=repo_id,
        job_id=job_id,
        local_path=local_path,
        artifact_path=artifact_path,
    )
