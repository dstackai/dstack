import os
from pathlib import Path
from typing import List, Optional

from tqdm import tqdm

from dstack._internal.backend.base import jobs
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.artifact import Artifact, ArtifactSpec
from dstack._internal.core.error import DstackError
from dstack._internal.utils.common import PathLike, removeprefix


class ArtifactsError(DstackError):
    pass


class ArtifactsUploadError(ArtifactsError):
    pass


class ArtifactsDownloadError(ArtifactsError):
    pass


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
    update_job: bool = True,
):
    local_path = Path(local_path).expanduser().absolute()
    if not local_path.exists():
        raise ArtifactsUploadError(f"Local path {local_path} does not exist")
    if not local_path.is_dir():
        raise ArtifactsUploadError(f"Local artifact path must be a directory")
    artifacts_dir = _get_job_artifacts_dir(repo_id, job_id)
    artifact_path = normalize_upload_artifact_path(artifact_path)
    relative_artifact_path = _relativize_upload_artifact_path(artifact_path)
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
                    artifacts_dir, relative_artifact_path, Path(filepath).relative_to(local_path)
                )
                storage.upload_file(source_path, dest_path, callback)
    if update_job:
        _update_job_artifacts(storage, repo_id, job_id, artifact_path)


def normalize_upload_artifact_path(path: PathLike) -> Path:
    path = Path(path).expanduser()
    _validate_upload_artifact_path(path)
    return path


def _validate_upload_artifact_path(path: Path):
    valid_path = path.absolute() == path or path.absolute().resolve() == Path.cwd() / path
    if not valid_path:
        raise ArtifactsUploadError(
            "Artifact path should be absolute or be inside the working directory."
        )


def _relativize_upload_artifact_path(path: Path) -> Path:
    return Path(str(path).lstrip("/"))


def _normalize_path_prefix(path: str) -> str:
    normalized_path = str(Path(path)).lstrip(".").lstrip(os.sep)
    if path.endswith("/"):
        normalized_path += "/"
    return normalized_path


def _update_job_artifacts(storage: Storage, repo_id: str, job_id: str, artifact_path: Path):
    artifact_path = str(artifact_path)
    job = jobs.get_job(storage, repo_id, job_id)
    if job.artifact_specs is None:
        job.artifact_specs = []
    artifact_paths = [s.artifact_path for s in job.artifact_specs]
    if artifact_path in artifact_paths:
        return
    job.artifact_specs.append(ArtifactSpec(artifact_path=artifact_path))
    jobs.update_job(storage, job)


def _get_artifacts_dir(repo_id: str) -> str:
    return f"artifacts/{repo_id}/"


def _get_job_artifacts_dir(repo_id: str, job_id: str) -> str:
    return f"{_get_artifacts_dir(repo_id)}{job_id}/"
