from typing import Optional, List

from botocore.client import BaseClient

from dstack import random_name
from dstack.aws import run_names, logs, jobs, runners
from dstack.backend import RunHead, AppHead, ArtifactHead
from dstack.jobs import JobHead, Job


def create_run(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_user_name: str,
               repo_name: str) -> str:
    name = random_name.next_name()
    run_name_index = run_names.next_run_name_index(s3_client, bucket_name, name)
    run_name = f"{name}-{run_name_index}"
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}"
    logs.create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)
    return run_name


def _create_run(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, job_head: JobHead,
                include_request_heads: bool) -> RunHead:
    app_heads = list(
        map(lambda app_name: AppHead(job_head.job_id, app_name), job_head.app_names)) if job_head.app_names else None
    artifact_heads = list(map(lambda artifact_path: ArtifactHead(job_head.job_id, artifact_path),
                              job_head.artifact_paths)) if job_head.artifact_paths else None
    request_heads = None
    if include_request_heads and job_head.status.is_unfinished():
        if request_heads is None:
            request_heads = []
        job = jobs.get_job(s3_client, bucket_name, job_head.repo_user_name, job_head.repo_name, job_head.job_id)
        request_head = runners.get_request_head(ec2_client, job)
        request_heads.append(request_head)
    run_head = RunHead(job_head.repo_user_name, job_head.repo_name, job_head.run_name, job_head.workflow_name,
                       job_head.provider_name, artifact_heads or None, job_head.status, job_head.submitted_at,
                       job_head.tag_name, app_heads, request_heads)
    return run_head


def _update_run(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, run: RunHead, job_head: JobHead,
                include_request_heads: bool):
    run.submitted_at = min(run.submitted_at, job_head.submitted_at)
    if job_head.artifact_paths:
        if run.artifact_heads is None:
            run.artifact_heads = []
        run.artifact_heads.extend(
            list(map(lambda artifact_path: ArtifactHead(job.job_id, artifact_path), job_head.artifact_paths)))
    if job_head.app_names:
        if run.app_heads is None:
            run.app_heads = []
        run.app_heads.extend(list(map(lambda app_name: AppHead(job.job_id, app_name), job_head.app_names)))
    if job_head.status.is_unfinished():
        run.status = job_head.status
        if include_request_heads:
            if run.request_heads is None:
                run.request_heads = []
            job = jobs.get_job(s3_client, bucket_name, job_head.repo_user_name, job_head.repo_name, job_head.job_id)
            request_head = runners.get_request_head(ec2_client, job)
            run.request_heads.append(request_head)


def get_run_heads(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
                  job_heads: List[JobHead], include_request_heads: bool) -> List[RunHead]:
    runs_by_id = {}
    for job_head in job_heads:
        run_id = ','.join([job_head.run_name, job_head.workflow_name or ''])
        if run_id not in runs_by_id:
            runs_by_id[run_id] = _create_run(ec2_client, s3_client, bucket_name, job_head, include_request_heads)
        else:
            run = runs_by_id[run_id]
            _update_run(ec2_client, s3_client, bucket_name, run, job_head, include_request_heads)
    return sorted(list(runs_by_id.values()), key=lambda r: r.submitted_at, reverse=True)


def list_run_heads(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
                   run_name: Optional[str], include_request_heads: bool) -> List[RunHead]:
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_user_name, repo_name, run_name)
    return get_run_heads(ec2_client, s3_client, bucket_name, repo_user_name, repo_name, job_heads,
                         include_request_heads)
