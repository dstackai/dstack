import os
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from dstack.backend.base import jobs
from dstack.backend.base.storage import Storage
from dstack.core.artifact import Artifact
from dstack.utils.common import PathLike, removeprefix


def list_run_artifact_files(
    storage: Storage, repo_id: str, run_name: str, prefix: str, recursive: bool
) -> List[Artifact]:
    normalized_prefix = _normalize_path_prefix(prefix)
    jobs_list = jobs.list_jobs(storage, repo_id, run_name)
    artifacts = []
    for job in jobs_list:
        if job.artifact_paths is None:
            continue
        job_artifacts_dir = _get_job_artifacts_dir(repo_id, job.job_id)
        for artifact_path in job.artifact_paths:
            artifact_name = os.path.join(artifact_path, "")
            artifact_path = os.path.join(_normalize_path_prefix(artifact_path), "")
            artifact_full_path = os.path.join(job_artifacts_dir, artifact_path)
            if artifact_path.startswith(normalized_prefix):
                files_path = artifact_full_path
            elif normalized_prefix.startswith(artifact_path):
                files_path = os.path.join(job_artifacts_dir, normalized_prefix)
            else:
                continue
            artifact_files = storage.list_files(files_path, recursive=recursive)
            if len(artifact_files) == 0:
                continue
            for file in artifact_files:
                file.filepath = removeprefix(file.filepath, artifact_full_path)
            artifact = Artifact(
                job_id=job.job_id,
                name=artifact_name,
                path=artifact_path,
                files=artifact_files,
            )
            artifacts.append(artifact)
    return artifacts


def download_run_artifact_files(
    storage: Storage,
    repo_id: str,
    artifacts: List[Artifact],
    output_dir: Optional[str],
    files_path: Optional[str],
):
    if output_dir is None:
        output_dir = os.getcwd()
    for artifact in artifacts:
        files = []
        for file in artifact.files:
            file_full_path = os.path.join(artifact.path, file.filepath)
            if (
                files_path is None
                or Path(file_full_path) == Path(files_path)
                or Path(files_path) in Path(file_full_path).parents
            ):
                files.append(file)
        if len(files) == 0:
            continue
        total_size = sum(f.filesize_in_bytes for f in files)
        with tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"Downloading artifact '{artifact.name}'",
        ) as pbar:

            def callback(size):
                pbar.update(size)

            for file in files:
                artifacts_dir = _get_job_artifacts_dir(repo_id, artifact.job_id)
                source_path = os.path.join(artifacts_dir, artifact.path, file.filepath)
                dest_path = os.path.join(output_dir, artifact.job_id, artifact.path, file.filepath)
                Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
                storage.download_file(source_path, dest_path, callback)


def upload_job_artifact_files(
    storage: Storage,
    repo_id: str,
    job_id: str,
    artifact_name: str,
    artifact_path: PathLike,
    local_path: PathLike,
):
    artifacts_dir = _get_job_artifacts_dir(repo_id, job_id)
    total_size = 0
    for root, sub_dirs, files in os.walk(local_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            file_size = os.path.getsize(file_path)
            total_size += file_size
    with tqdm(
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc=f"Uploading artifact '{artifact_name}'",
    ) as pbar:

        def callback(size):
            pbar.update(size)

        for root, sub_dirs, files in os.walk(local_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                source_path = filepath
                dest_path = os.path.join(
                    artifacts_dir, artifact_path, Path(filepath).relative_to(local_path)
                )
                storage.upload_file(source_path, dest_path, callback)


def _normalize_path_prefix(path: str) -> str:
    normalized_path = str(Path(path)).lstrip(".").lstrip(os.sep)
    if path.endswith("/"):
        normalized_path += "/"
    return normalized_path


def _get_artifacts_dir(repo_id: str) -> str:
    return f"artifacts/{repo_id}/"


def _get_job_artifacts_dir(repo_id: str, job_id: str) -> str:
    return f"{_get_artifacts_dir(repo_id)}{job_id}/"
