import sys
import time
from pathlib import Path
from typing import Optional, List

from botocore.client import BaseClient

from dstack.aws import jobs, runs, artifacts
from dstack.backend import TagHead, BackendError
from dstack.jobs import Job, JobStatus
from dstack.repo import RepoData


def list_tag_heads(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str):
    prefix = f"tags/{repo_user_name}/{repo_name}"
    tag_head_prefix = f"{prefix}/l;"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    tag_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            tag_name, run_name, workflow_name, provider_name, created_at, artifacts = tuple(
                obj["Key"][len(tag_head_prefix):].split(';'))
            tag_heads.append(TagHead(repo_user_name, repo_name,
                                     tag_name, run_name, workflow_name, provider_name, int(created_at),
                                     artifacts.split(',') if artifacts else None))
    return tag_heads


def get_tag_head(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, tag_name: str) -> \
        Optional[TagHead]:
    prefix = f"tags/{repo_user_name}/{repo_name}"
    tag_head_prefix = f"{prefix}/l;{tag_name};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    if "Contents" in response:
        run_name, workflow_name, provider_name, created_at, artifacts = tuple(
            response["Contents"][0]["Key"][len(tag_head_prefix):].split(';'))
        return TagHead(repo_user_name, repo_name,
                       tag_name, run_name, workflow_name, provider_name, int(created_at),
                       artifacts.split(',') if artifacts else None)
    else:
        return None


def _tag_head_key(tag_head: TagHead) -> str:
    prefix = f"tags/{tag_head.repo_user_name}/{tag_head.repo_name}"
    key = f"{prefix}/l;{tag_head.tag_name};" \
          f"{tag_head.run_name};" \
          f"{tag_head.workflow_name or ''};" \
          f"{tag_head.provider_name or ''};" \
          f"{tag_head.created_at};" \
          f"{','.join(tag_head.artifacts) if tag_head.artifacts else ''}"
    return key


def create_tag_from_run(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                        tag_name: str, run_name: str):
    tag_jobs = []
    job_with_anther_tag = None
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_user_name, repo_name, run_name)
    for job_head in job_heads:
        job = jobs.get_job(s3_client, bucket_name, repo_user_name, repo_name, job_head.id)
        tag_jobs.append(job)
        if job.tag_name and job.tag_name != tag_name:
            job_with_anther_tag = job
    if job_with_anther_tag:
        raise BackendError(f"The run '{job_with_anther_tag.run_name} refers to another tag: "
                           f"{job_with_anther_tag.tag_name}'")
    if not tag_jobs:
        sys.exit(f"Cannot find the run {run_name}")
    tag_head = TagHead(repo_user_name, repo_name, tag_name, run_name, tag_jobs[0].workflow_name,
                       tag_jobs[0].provider_name, int(round(time.time() * 1000)),
                       [artifact for run_job in tag_jobs for artifact in run_job.artifacts])
    s3_client.put_object(Body="", Bucket=bucket_name, Key=_tag_head_key(tag_head))

    for job in tag_jobs:
        job.tag_name = tag_name
        jobs.update_job(s3_client, bucket_name, job)


def delete_tag(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, tag_head: TagHead):
    tag_jobs = []
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_user_name, repo_name, tag_head.run_name)
    for job_head in job_heads:
        job = jobs.get_job(s3_client, bucket_name, repo_user_name, repo_name, job_head.id)
        tag_jobs.append(job)
    s3_client.delete_object(Bucket=bucket_name, Key=_tag_head_key(tag_head))
    for job in tag_jobs:
        job.tag_name = None
        jobs.update_job(s3_client, bucket_name, job)


def create_tag_from_local_dirs(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_data: RepoData,
                               tag_name: str, local_dirs: List[str]):
    local_paths = []
    tag_artifacts = []
    for local_dir in local_dirs:
        path = Path(local_dir)
        if path.is_dir():
            local_paths.append(path)
            tag_artifacts.append(path.name)
        else:
            sys.exit(f"The '{local_dir}' path doesn't refer to an existing directory")

    run_name = runs.create_run(s3_client, logs_client, bucket_name, repo_data.repo_user_name, repo_data.repo_name)
    job = Job(repo_data, run_name, None, "bash", JobStatus.DONE, int(round(time.time() * 1000)), "scratch",
              None, None, None, tag_artifacts, None, None, None, None, None, None, None, None, None, tag_name)
    jobs.create_job(s3_client, bucket_name, job, create_head=False)
    for index, local_path in enumerate(local_paths):
        artifacts.upload_job_artifact_files(s3_client, bucket_name, repo_data.repo_user_name, repo_data.repo_name,
                                            job.id, tag_artifacts[index], local_path)
    tag_head = TagHead(repo_data.repo_user_name, repo_data.repo_name, tag_name, run_name, job.workflow_name,
                       job.provider_name, job.submitted_at, job.artifacts)
    lKey = _tag_head_key(tag_head)
    s3_client.put_object(Body="", Bucket=bucket_name, Key=lKey)
