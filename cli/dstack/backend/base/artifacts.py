import os
from typing import List

from dstack.backend.base import jobs
from dstack.backend.base.storage import Storage
from dstack.core.artifact import Artifact
from dstack.core.job import Job
from dstack.core.repo import RepoAddress


def list_run_artifact_files(
    storage: Storage, repo_address: RepoAddress, run_name: str
) -> List[Artifact]:
    jobs_list = jobs.list_jobs(storage, repo_address, run_name)
    artifacts = []
    for job in jobs_list:
        job_artifacts_dir = _get_job_artifacts_dir(job)
        for artifact_path in job.artifact_paths:
            artifact_path = os.path.join(artifact_path, "")
            job_artifact_files_path = os.path.join(job_artifacts_dir, artifact_path)
            artifact_files = storage.list_files(job_artifact_files_path)
            for artifact_file in artifact_files:
                artifact = Artifact(
                    job_id=job.job_id,
                    name=artifact_path,
                    file=artifact_file.filepath,
                    filesize_in_bytes=artifact_file.filesize_in_bytes,
                )
                artifacts.append(artifact)
    return artifacts


def _get_artifacts_dir(repo_address: RepoAddress) -> str:
    return f"artifacts/{repo_address.path()}/"


def _get_job_artifacts_dir(job_head: Job) -> str:
    return f"{_get_artifacts_dir(job_head.repo_address)}{job_head.job_id}/"
