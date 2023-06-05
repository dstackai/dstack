from typing import Optional

from dstack._internal.api import workflow_api
from dstack._internal.api.artifacts import (
    download_artifact_files_backend,
    upload_artifact_files_backend,
    upload_artifact_files_from_tag_backend,
)
from dstack._internal.api.runs import get_tagged_run_name_backend


def download(
    run: Optional[str] = None,
    tag: Optional[str] = None,
    artifact_path: Optional[str] = None,
    local_path: Optional[str] = None,
):
    if artifact_path is None:
        artifact_path = ""
        local_path = "."
    if local_path is None:
        local_path = artifact_path
    backend = workflow_api.get_current_backend()
    repo_id = workflow_api.get_current_repo_id()
    run_name, _ = get_tagged_run_name_backend(
        backend=backend,
        repo_id=repo_id,
        run_name=run,
        tag_name=tag,
    )
    download_artifact_files_backend(
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
    if tag is None:
        upload_artifact_files_backend(
            backend=backend,
            repo_id=repo_id,
            job_id=job_id,
            local_path=local_path,
            artifact_path=artifact_path,
        )
        return
    job = workflow_api.get_current_job()
    upload_artifact_files_from_tag_backend(
        backend=backend,
        repo=job.repo,
        hub_user_name=job.hub_user_name,
        local_path=local_path,
        artifact_path=artifact_path,
        tag_name=tag,
    )
