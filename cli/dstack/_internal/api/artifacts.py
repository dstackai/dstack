import os
import shutil
import sys
from functools import partial
from pathlib import Path

from dstack._internal.backend.base import Backend
from dstack._internal.backend.base.artifacts import ArtifactsDownloadError, ArtifactsUploadError
from dstack._internal.core.error import DstackError
from dstack._internal.core.repo.base import Repo
from dstack._internal.utils.common import get_dstack_dir
from dstack.api.hub import HubClient


def download_artifact_files_hub(hub_client: HubClient, run_name: str, source: str, target: str):
    _download_artifact_files(
        download_run_artifact_files_func=hub_client.download_run_artifact_files,
        repo_id=hub_client.repo.repo_id,
        run_name=run_name,
        source=source,
        target=target,
    )


def download_artifact_files_backend(
    backend: Backend, repo_id: str, run_name: str, source: str, target: str
):
    download_run_artifact_files_func = partial(
        backend.download_run_artifact_files, repo_id=repo_id
    )
    _download_artifact_files(
        download_run_artifact_files_func=download_run_artifact_files_func,
        repo_id=repo_id,
        run_name=run_name,
        source=source,
        target=target,
    )


def upload_artifact_files_backend(
    backend: Backend, repo_id: str, job_id: str, local_path: str, artifact_path: str
):
    backend.upload_job_artifact_files(
        repo_id=repo_id,
        job_id=job_id,
        artifact_name=artifact_path,
        artifact_path=artifact_path,
        local_path=local_path,
    )


def upload_artifact_files_from_tag_backend(
    backend: Backend,
    repo: Repo,
    hub_user_name: str,
    local_path: str,
    artifact_path: str,
    tag_name: str,
):
    if backend.get_tag_head(repo_id=repo.repo_id, tag_name=tag_name) is not None:
        raise DstackError(f"Tag {tag_name} already exists")
    backend.add_tag_from_local_dirs(
        repo=repo,
        hub_user_name=hub_user_name,
        tag_name=tag_name,
        local_dirs=[local_path],
        artifact_paths=[artifact_path],
    )


def _download_artifact_files(
    download_run_artifact_files_func, repo_id: str, run_name: str, source: str, target: str
):
    tmp_output_dir = get_dstack_dir() / "tmp" / "copied_artifacts" / repo_id
    tmp_output_dir.mkdir(parents=True, exist_ok=True)
    source = _normalize_source(source)
    download_run_artifact_files_func(
        run_name=run_name,
        output_dir=tmp_output_dir,
        files_path=source,
    )
    tmp_job_output_dir = None
    # TODO: We support copy for a single job.
    # Decide later how to work with multi-job artifacts.
    for job_dir in os.listdir(tmp_output_dir):
        if job_dir.startswith(run_name):
            tmp_job_output_dir = tmp_output_dir / job_dir
            break
    if tmp_job_output_dir is None:
        raise ArtifactsDownloadError(f"Artifact source path '{source}' does not exist")

    source_full_path = tmp_job_output_dir / source
    target_path = Path(target)
    if source_full_path.is_dir():
        if target_path.exists() and not target_path.is_dir():
            shutil.rmtree(tmp_job_output_dir)
            raise ArtifactsDownloadError(
                f"Local target path '{target}' exists and is not a directory"
            )
        if sys.version_info[1] >= 8:
            shutil.copytree(source_full_path, target, dirs_exist_ok=True)
        else:  # todo: drop along with 3.7
            import distutils.dir_util

            distutils.dir_util.copy_tree(source_full_path, target)
    else:
        if not target_path.exists():
            if target.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_full_path, target_path)
    shutil.rmtree(tmp_job_output_dir)


def _normalize_source(source: str) -> str:
    source = str(Path(source))
    if source.startswith("/"):
        source = source[1:]
    return source
