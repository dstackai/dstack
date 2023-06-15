from typing import Optional

from dstack._internal.api import workflow_api
from dstack._internal.api.artifacts import (
    download_artifact_files_backend,
    upload_artifact_files_backend,
    upload_artifact_files_from_tag_backend,
)
from dstack._internal.api.runs import get_tagged_run_name_backend


def upload(local_path: str, artifact_path: Optional[str] = None, tag: Optional[str] = None):
    """Uploads files located at `local_path` as the artifacts of the current run.
    If `tag` is specified, uploads the files as the artifacts of the tag instead.
    By default, artifact files saved under the same path as `local_path`.
    The `artifact_path` parameter can be used to specify a different artifact path.

    Examples:
    ```python
    from dstack import artifacts

    # Uploads local_path as an artifact of the current run
    artifacts.upload(local_path="datasets/dataset1")

    # Uploads local_path as an artifact of a new run tagged as my_tag and saves it as artifact_path
    artifacts.upload(local_path="datasets/dataset1", artifact_path="data", tag="my_tag")
    ```

    :param local_path: The local path to upload the files from
    :type local_path: str
    :param artifact_path: The path under which the files will be stored
    :type artifact_path: Optional[str]
    :param tag: The tag to assign the artifacts, defaults to None
    :type tag: Optional[str]
    :raises ArtifactsUploadError: Raises if cannot upload the artifacts
    :raises DstackError: The base exception for all dstack errors
    """
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


def download(
    run: Optional[str] = None,
    tag: Optional[str] = None,
    artifact_path: Optional[str] = None,
    local_path: Optional[str] = None,
):
    """Downloads artifact files of a run or a tag.
    The files are downloaded from `artifact_path` to `local_path`.
    By default, downloads all the files and saves them to the current directory.

    Examples:
    ```python
    from dstack import artifacts

    # Downloads all artifact files of a run
    artifacts.download(run="sharp-shrimp-1")

    # Downloads artifact files from artifact_path and saves them to local_path
    artifacts.download(tag="my_tag", artifact_path="output/my_model", local_path="./my_model")
    ```

    :param run: The run to download the artifacts from
    :type run: Optional[str]
    :param tag: The tag to download the artifacts from
    :type tag: Optional[str]
    :param artifact_path: The path to artifact files to download, defaults to ""
    :type artifact_path: Optional[str]
    :param local_path: The local path to save the files to, defaults to "."
    :type local_path: Optional[str]
    :raises ArtifactsDownloadError: Raises if cannot download the artifacts
    :raises DstackError: The base exception for all dstack errors
    """
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
