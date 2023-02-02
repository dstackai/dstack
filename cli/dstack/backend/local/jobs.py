from typing import List, Optional, Dict, Any
import os
from pathlib import Path
import yaml

from dstack.backend.local.common import (
    list_objects,
    put_object,
    get_object,
    delete_object,
)
from dstack.core.job import Job, JobStatus, JobHead
from dstack.core.repo import RepoAddress


def list_job_heads(
    path: str, repo_address: RepoAddress, run_name: Optional[str] = None
) -> List[JobHead]:
    root = os.path.join(path, "jobs", repo_address.path())
    job_head_key_prefix = "l;"
    job_head_key_run_prefix = job_head_key_prefix + run_name if run_name else job_head_key_prefix
    response = list_objects(Root=root, Prefix=job_head_key_run_prefix)
    job_heads = []
    for obj in response:
        t = obj[len(job_head_key_prefix) :].split(";")
        if len(t) == 8:
            (
                job_id,
                provider_name,
                local_repo_user_name,
                submitted_at,
                status,
                artifacts,
                app_names,
                tag_name,
            ) = tuple(t)
            run_name, workflow_name, job_index = tuple(job_id.split(","))
            job_heads.append(
                JobHead(
                    job_id,
                    repo_address,
                    run_name,
                    workflow_name or None,
                    provider_name,
                    local_repo_user_name,
                    JobStatus(status),
                    int(submitted_at),
                    artifacts.split(",") if artifacts else None,
                    tag_name or None,
                    app_names.split(",") or None,
                )
            )
    return job_heads


def create_job(path: str, job: Job, counter: List[int] = [], create_head: bool = True):
    if len(counter) == 0:
        counter.append(0)
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
    job.set_id(job_id)
    root = os.path.join(path, "jobs", job.repo_address.path())
    if create_head:
        put_object(Body="", Root=root, Key=job.job_head_key(add_prefix=False))
    key = f"{job_id}.yaml"
    put_object(Body=yaml.dump(job.serialize()), Root=root, Key=key)
    counter[0] += 1


def get_job(path: str, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
    root = os.path.join(path, "jobs", repo_address.path())
    key = f"{job_id}.yaml"
    try:
        obj = get_object(Root=root, Key=key)
        job = Job.unserialize(yaml.load(obj, yaml.FullLoader))
        return job
    except IOError as e:
        return None


def update_job(path: str, job: Job):
    root = os.path.join(path, "jobs", job.repo_address.path())
    job_head_key_prefix = f"l;{job.job_id};"
    response = list_objects(Root=root, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response:
        delete_object(Root=root, Key=obj)
    put_object(Body="", Root=root, Key=job.job_head_key(add_prefix=False))
    key = f"{job.job_id}.yaml"
    put_object(Body=yaml.dump(job.serialize()), Root=root, Key=key)


def list_job_head(path: str, repo_address: RepoAddress, job_id: str) -> Optional[JobHead]:
    root = os.path.join(path, "jobs", repo_address.path())
    job_head_key_prefix = f"l;{job_id};"
    response = list_objects(Root=root, Prefix=job_head_key_prefix)
    for obj in response:
        t = obj[len(job_head_key_prefix) :].split(";")
        if len(t) == 7:
            (
                provider_name,
                local_repo_user_name,
                submitted_at,
                status,
                artifacts,
                app_names,
                tag_name,
            ) = tuple(t)
            run_name, workflow_name, job_index = tuple(job_id.split(","))
            return JobHead(
                job_id,
                repo_address,
                run_name,
                workflow_name or None,
                provider_name,
                local_repo_user_name or None,
                JobStatus(status),
                int(submitted_at),
                artifacts.split(",") if artifacts else None,
                tag_name or None,
                app_names.split(",") or None,
            )
    return None


def list_jobs(path: str, repo_address: RepoAddress, run_name: Optional[str] = None) -> List[Job]:
    root = os.path.join(path, "jobs", repo_address.path())
    job_key_run_prefix = f"{run_name},"
    response = list_objects(Root=root, Prefix=job_key_run_prefix)
    jobs = []
    for obj in response:
        job_obj = get_object(Root=root, Key=obj)
        job = Job.unserialize(yaml.load(job_obj, yaml.FullLoader))
        jobs.append(job)
    return jobs


def delete_job_head(path: str, repo_address: RepoAddress, job_id: str):
    root = os.path.join(path, "jobs", repo_address.path())
    job_head_key_prefix = f"l;{job_id};"
    response = list_objects(Root=root, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response:
        delete_object(Root=root, Key=obj)


def store_job(dstack_dir: Path, job: Job):
    create_job(dstack_dir, job)
