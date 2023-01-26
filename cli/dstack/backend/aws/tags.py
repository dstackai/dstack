import sys
import time
from pathlib import Path
from typing import Optional, List

from botocore.client import BaseClient

from dstack.backend.aws import jobs, runs, artifacts, repos
from dstack.core.tag import TagHead
from dstack.core.artifact import ArtifactHead, ArtifactSpec
from dstack.core.error import BackendError
from dstack.core.job import Job, JobStatus
from dstack.core.repo import RepoAddress, _repo_address_path, LocalRepoData


def _unserialize_artifact_heads(artifact_heads):
    return [ArtifactHead(a.split("=")[0], a.split("=")[1]) for a in
            artifact_heads.split(':')] if artifact_heads else None


def list_tag_heads(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress):
    prefix = f"tags/{_repo_address_path(repo_address)}"
    tag_head_prefix = f"{prefix}/l;"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    tag_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            t = obj["Key"][len(tag_head_prefix):].split(';')
            if len(t) == 7:
                tag_name, run_name, workflow_name, provider_name, local_repo_user_name, created_at, artifact_heads = tuple(
                    t)
                tag_heads.append(TagHead(repo_address, tag_name, run_name, workflow_name or None, provider_name or None,
                                         local_repo_user_name or None, int(created_at),
                                         _unserialize_artifact_heads(artifact_heads)))
    return tag_heads


def get_tag_head(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, tag_name: str) \
        -> Optional[TagHead]:
    prefix = f"tags/{_repo_address_path(repo_address)}"
    tag_head_prefix = f"{prefix}/l;{tag_name};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=tag_head_prefix)
    if response.get("Contents"):
        t = response["Contents"][0]["Key"][len(tag_head_prefix):].split(';')
        if len(t) == 6:
            run_name, workflow_name, provider_name, local_repo_user_name, created_at, artifact_heads = tuple(t)
            return TagHead(repo_address, tag_name, run_name, workflow_name or None, provider_name or None,
                           local_repo_user_name or None, int(created_at), _unserialize_artifact_heads(artifact_heads))
    else:
        return None


def _serialize_artifact_heads(tag_head):
    return ':'.join(
        [a.job_id + '=' + a.artifact_path for a in tag_head.artifact_heads]) if tag_head.artifact_heads else ''


def _tag_head_key(tag_head: TagHead) -> str:
    prefix = f"tags/{_repo_address_path(tag_head.repo_address)}"
    key = f"{prefix}/l;{tag_head.tag_name};" \
          f"{tag_head.run_name};" \
          f"{tag_head.workflow_name or ''};" \
          f"{tag_head.provider_name or ''};" \
          f"{tag_head.local_repo_user_name or ''};" \
          f"{tag_head.created_at};" \
          f"{_serialize_artifact_heads(tag_head)}"
    return key


def create_tag_from_run(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress,
                        tag_name: str, run_name: str, run_jobs: Optional[List[Job]]):
    if run_jobs:
        tag_jobs = run_jobs
    else:
        tag_jobs = []
        job_with_anther_tag = None
        job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_address, run_name)
        for job_head in job_heads:
            job = jobs.get_job(s3_client, bucket_name, repo_address, job_head.job_id)
            if job:
                tag_jobs.append(job)
                if job.tag_name and job.tag_name != tag_name:
                    job_with_anther_tag = job
        if job_with_anther_tag:
            raise BackendError(f"The run '{job_with_anther_tag.run_name} refers to another tag: "
                               f"{job_with_anther_tag.tag_name}'")
        if not tag_jobs:
            sys.exit(f"Cannot find the run '{run_name}'")

    tag_head = TagHead(repo_address, tag_name, run_name, tag_jobs[0].workflow_name, tag_jobs[0].provider_name,
                       tag_jobs[0].local_repo_user_name, int(round(time.time() * 1000)),
                       [ArtifactHead(run_job.job_id, artifact_spec.artifact_path) for run_job in tag_jobs for
                        artifact_spec in run_job.artifact_specs or []] or None)
    s3_client.put_object(Body="", Bucket=bucket_name, Key=_tag_head_key(tag_head))

    if not run_jobs:
        for job in tag_jobs:
            job.tag_name = tag_name
            jobs.update_job(s3_client, bucket_name, job)
    repos.increment_repo_tags_count(s3_client, bucket_name, repo_address)


def delete_tag(s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, tag_head: TagHead):
    tag_jobs = []
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_address, tag_head.run_name)
    for job_head in job_heads:
        job = jobs.get_job(s3_client, bucket_name, repo_address, job_head.job_id)
        if job:
            tag_jobs.append(job)
    s3_client.delete_object(Bucket=bucket_name, Key=_tag_head_key(tag_head))
    for job in tag_jobs:
        job.tag_name = None
        jobs.update_job(s3_client, bucket_name, job)
    repos.decrement_repo_tags_count(s3_client, bucket_name, repo_address)


def create_tag_from_local_dirs(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str,
                               repo_data: LocalRepoData, tag_name: str, local_dirs: List[str]):
    local_paths = []
    tag_artifacts = []
    for local_dir in local_dirs:
        path = Path(local_dir)
        if path.is_dir():
            local_paths.append(path)
            tag_artifacts.append(path.name)
        else:
            sys.exit(f"The '{local_dir}' path doesn't refer to an existing directory")

    run_name = runs.create_run(s3_client, logs_client, bucket_name, repo_data)
    job = Job(None, repo_data, run_name, None, "bash", repo_data.local_repo_user_name, repo_data.local_repo_user_email,
              JobStatus.DONE, int(round(time.time() * 1000)), "scratch", None, None, None,
              [ArtifactSpec(a, False) for a in tag_artifacts], None, None, None, None, None, None, None, None, None,
              tag_name)
    jobs.create_job(s3_client, bucket_name, job, create_head=False)
    for index, local_path in enumerate(local_paths):
        artifacts.upload_job_artifact_files(s3_client, bucket_name, repo_data, job.job_id, tag_artifacts[index],
                                            local_path)
    tag_head = TagHead(repo_data, tag_name, run_name, job.workflow_name, job.provider_name, job.local_repo_user_name,
                       job.submitted_at, [ArtifactHead(job.job_id, a.artifact_path) for a in
                                          job.artifact_specs] if job.artifact_specs else None)
    tag_head_key = _tag_head_key(tag_head)
    s3_client.put_object(Body="", Bucket=bucket_name, Key=tag_head_key)
    repos.increment_repo_tags_count(s3_client, bucket_name, repo_data)
