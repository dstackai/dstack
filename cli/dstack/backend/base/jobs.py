from typing import List, Optional

import yaml

from dstack.backend.base.storage import Storage
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.repo import RepoAddress


def create_job(
    storage: Storage,
    job: Job,
    create_head: bool = True,
):
    if create_head:
        storage.put_object(key=_get_job_head_filename(job), content="")
    storage.put_object(
        key=_get_job_filename(job.repo_address, job.job_id), content=yaml.dump(job.serialize())
    )


def get_job(storage: Storage, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
    obj = storage.get_object(_get_job_filename(repo_address, job_id))
    if obj is None:
        return None
    job = Job.unserialize(yaml.load(obj, yaml.FullLoader))
    return job


def update_job(storage: Storage, job: Job):
    job_head_key_prefix = _get_job_head_filename_prefix(job.repo_address, job.job_id)
    job_keys = storage.list_objects(job_head_key_prefix)
    for key in job_keys:
        storage.delete_object(key)
    storage.put_object(key=_get_job_head_filename(job), content="")
    storage.put_object(key=_get_job_filename(job), content=yaml.dump(job.serialize()))


def list_jobs(
    storage: Storage,
    repo_address: RepoAddress,
    run_name: str,
) -> List[Job]:
    job_key_run_prefix = _get_jobs_filenames_prefix(repo_address, run_name)
    jobs_keys = storage.list_objects(job_key_run_prefix)
    jobs = []
    for job_key in jobs_keys:
        job_obj = storage.get_object(job_key)
        job = Job.unserialize(yaml.load(job_obj, yaml.FullLoader))
        jobs.append(job)
    return jobs


def list_job_head(storage: Storage, repo_address: RepoAddress, job_id: str) -> Optional[JobHead]:
    job_head_key_prefix = _get_job_head_filename_prefix(repo_address, job_id)
    job_head_keys = storage.list_objects(job_head_key_prefix)
    for job_head_key in job_head_keys:
        t = job_head_key[len(job_head_key_prefix) :].split(";")
        # Skip legacy format
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


def list_job_heads(
    storage: Storage,
    repo_address: RepoAddress,
    run_name: Optional[str] = None,
) -> List[JobHead]:
    job_heads_keys_prefix = _get_job_heads_filenames_prefix(repo_address, run_name)
    job_heads_keys = storage.list_objects(job_heads_keys_prefix)
    job_heads = []
    for job_head_key in job_heads_keys:
        t = job_head_key[len(_get_jobs_dir(repo_address)) :].split(";")
        # Skip legacy format
        if len(t) == 9:
            (
                _,
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


def delete_job_head(storage: Storage, repo_address: RepoAddress, job_id: str):
    job_head_key_prefix = _get_job_head_filename_prefix(repo_address, job_id)
    job_head_keys = storage.list_objects(job_head_key_prefix)
    for job_head_key in job_head_keys:
        storage.delete_object(job_head_key)


def _get_jobs_dir(repo_address: RepoAddress) -> str:
    return f"jobs/{repo_address.path()}/"


def _get_job_filename(repo_address: RepoAddress, job_id: str) -> str:
    return f"{_get_jobs_dir(repo_address)}{job_id}.yaml"


def _get_jobs_filenames_prefix(repo_address: RepoAddress, run_name: str) -> str:
    return f"{_get_jobs_dir(repo_address)}{run_name},"


def _get_job_heads_filenames_prefix(repo_address: RepoAddress, run_name: Optional[str]) -> str:
    return f"{_get_jobs_dir(repo_address)}l;{run_name or ''}"


def _get_job_head_filename_prefix(repo_address: RepoAddress, job_id: str) -> str:
    prefix = _get_jobs_dir(repo_address)
    key = f"{prefix}l;" f"{job_id};"
    return key


def _get_job_head_filename(job: Job) -> str:
    prefix = _get_jobs_dir(job.repo_address)
    key = (
        f"{prefix}l;"
        f"{job.job_id};"
        f"{job.provider_name};"
        f"{job.local_repo_user_name or ''};"
        f"{job.submitted_at};"
        f"{job.status.value};"
        f"{','.join([a.artifact_path.replace('/', '_') for a in (job.artifact_specs or [])])};"
        f"{','.join([a.app_name for a in (job.app_specs or [])])};"
        f"{job.tag_name or ''}"
    )
    return key
