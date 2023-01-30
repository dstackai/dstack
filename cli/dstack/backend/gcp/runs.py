from typing import List

from google.cloud.storage import Bucket

from dstack import random_name
from dstack.backend import JobHead, RepoAddress, RunHead
from dstack.core.run import RunHead, ArtifactHead
from dstack.core.app import AppHead
from dstack.backend.gcp import storage


def create_run(bucket: Bucket) -> str:
    run_name_prefix = random_name.next_name()
    run_name_count = 0
    storage.put_object(bucket, f"run-names/{run_name_prefix}.yaml", '')
    run_name = f"{run_name_prefix}-{run_name_count+1}"
    return run_name


def get_run_heads(
    bucket: Bucket, repo_address: RepoAddress, job_heads: List[JobHead],
    include_request_heads: bool = True
) -> List[RunHead]:
    # TODO aggregate jobs of the same run
    return [_get_run_head(bucket, job_head, include_request_heads) for job_head in job_heads]


def _get_run_head(bucket: Bucket, job_head: JobHead, include_request_heads: bool) -> RunHead:
    app_heads = list(
        map(lambda app_name: AppHead(job_head.job_id, app_name), job_head.app_names)) if job_head.app_names else None
    artifact_heads = list(map(lambda artifact_path: ArtifactHead(job_head.job_id, artifact_path),
                              job_head.artifact_paths)) if job_head.artifact_paths else None
    request_heads = None
    if include_request_heads and job_head.status.is_unfinished():
        if request_heads is None:
            request_heads = []
        # TODO request heads
    run_head = RunHead(job_head.repo_address, job_head.run_name, job_head.workflow_name, job_head.provider_name,
                       job_head.local_repo_user_name, artifact_heads or None, job_head.status, job_head.submitted_at,
                       job_head.tag_name, app_heads, request_heads)
    return run_head
