import sys
import time
import os
from typing import Optional, List
from pathlib import Path

from dstack.backend.local.common import (
    list_objects,
    put_object,
    get_object,
    delete_object,
)
from dstack.backend.local import jobs, runs, artifacts, repos
from dstack.core.tag import TagHead
from dstack.core.artifact import ArtifactHead, ArtifactSpec
from dstack.core.error import BackendError
from dstack.core.job import Job, JobStatus
from dstack.core.repo import RepoAddress, RepoData


def _unserialize_artifact_heads(artifact_heads):
    return (
        [ArtifactHead(a.split("=")[0], a.split("=")[1]) for a in artifact_heads.split(":")]
        if artifact_heads
        else None
    )


def list_tag_heads(path: str, repo_address: RepoAddress):
    root = os.path.join(path, "tags", repo_address.path())
    tag_head_prefix = f"l;"
    response = list_objects(Root=root, Prefix=tag_head_prefix)
    tag_heads = []
    for obj in response:
        t = obj[len(tag_head_prefix) :].split(";")
        if len(t) == 7:
            (
                tag_name,
                run_name,
                workflow_name,
                provider_name,
                local_repo_user_name,
                created_at,
                artifact_heads,
            ) = tuple(t)
            tag_heads.append(
                TagHead(
                    repo_address,
                    tag_name,
                    run_name,
                    workflow_name or None,
                    provider_name or None,
                    local_repo_user_name or None,
                    int(created_at),
                    _unserialize_artifact_heads(artifact_heads),
                )
            )
    return tag_heads


def get_tag_head(path: str, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
    root = os.path.join(path, "tags", repo_address.path())
    tag_head_prefix = f"l;{tag_name};"
    response = list_objects(Root=root, Prefix=tag_head_prefix)
    if len(response) != 0:
        t = response[0][len(tag_head_prefix) :].split(";")
        if len(t) == 6:
            (
                run_name,
                workflow_name,
                provider_name,
                local_repo_user_name,
                created_at,
                artifact_heads,
            ) = tuple(t)
            return TagHead(
                repo_address,
                tag_name,
                run_name,
                workflow_name or None,
                provider_name or None,
                local_repo_user_name or None,
                int(created_at),
                _unserialize_artifact_heads(artifact_heads),
            )
    else:
        return None


def create_tag_from_run(
    path: str,
    repo_address: RepoAddress,
    tag_name: str,
    run_name: str,
    run_jobs: Optional[List[Job]],
):
    if run_jobs:
        tag_jobs = run_jobs
    else:
        tag_jobs = []
        job_with_anther_tag = None
        job_heads = jobs.list_job_heads(path, repo_address, run_name)
        for job_head in job_heads:
            job = jobs.get_job(path, repo_address, job_head.job_id)
            if job:
                tag_jobs.append(job)
                if job.tag_name and job.tag_name != tag_name:
                    job_with_anther_tag = job
        if job_with_anther_tag:
            raise BackendError(
                f"The run '{job_with_anther_tag.run_name} refers to another tag: "
                f"{job_with_anther_tag.tag_name}'"
            )
        if not tag_jobs:
            sys.exit(f"Cannot find the run '{run_name}'")

    root = os.path.join(path, "tags", repo_address.path())
    tag_head = TagHead(
        repo_address,
        tag_name,
        run_name,
        tag_jobs[0].workflow_name,
        tag_jobs[0].provider_name,
        tag_jobs[0].local_repo_user_name,
        int(round(time.time() * 1000)),
        [
            ArtifactHead(run_job.job_id, artifact_spec.artifact_path)
            for run_job in tag_jobs
            for artifact_spec in run_job.artifact_specs or []
        ]
        or None,
    )
    put_object(Body="", Root=root, Key=tag_head.key(add_prefix=False))

    if not run_jobs:
        for job in tag_jobs:
            job.tag_name = tag_name
            jobs.update_job(path, job)
    repos.increment_repo_tags_count(path, repo_address)


def delete_tag(path: str, repo_address: RepoAddress, tag_head: TagHead):
    root = os.path.join(path, "tags", repo_address.path())
    tag_jobs = []
    job_heads = jobs.list_job_heads(path, repo_address, tag_head.run_name)
    for job_head in job_heads:
        job = jobs.get_job(path, repo_address, job_head.job_id)
        if job:
            tag_jobs.append(job)
    delete_object(Root=root, Key=tag_head.key(add_prefix=False))
    for job in tag_jobs:
        job.tag_name = None
        jobs.update_job(path, job)
    repos.decrement_repo_tags_count(path, repo_address)


def create_tag_from_local_dirs(
    path: str, repo_data: RepoData, tag_name: str, local_dirs: List[str]
):
    root = os.path.join(path, "tags", repo_data.path())
    local_paths = []
    tag_artifacts = []
    for local_dir in local_dirs:
        path = Path(local_dir)
        if path.is_dir():
            local_paths.append(path)
            tag_artifacts.append(path.name)
        else:
            sys.exit(f"The '{local_dir}' path doesn't refer to an existing directory")

    run_name = runs.create_run(path, repo_data)
    job = Job(
        None,
        repo_data,
        run_name,
        None,
        "bash",
        repo_data.local_repo_user_name,
        repo_data.local_repo_user_email,
        JobStatus.DONE,
        int(round(time.time() * 1000)),
        "scratch",
        None,
        None,
        None,
        [ArtifactSpec(a, False) for a in tag_artifacts],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        tag_name,
    )
    jobs.create_job(path, job, create_head=False)
    for index, local_path in enumerate(local_paths):
        artifacts.upload_job_artifact_files(
            path, repo_data, job.job_id, tag_artifacts[index], local_path
        )
    tag_head = TagHead(
        repo_data,
        tag_name,
        run_name,
        job.workflow_name,
        job.provider_name,
        job.local_repo_user_name,
        job.submitted_at,
        [ArtifactHead(job.job_id, a.artifact_path) for a in job.artifact_specs]
        if job.artifact_specs
        else None,
    )
    put_object(Body="", Root=root, Key=tag_head.key(add_prefix=False))
    repos.increment_repo_tags_count(path, repo_data)
