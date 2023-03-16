import uuid
from typing import List, Optional

import yaml

from dstack.backend.base import runners
from dstack.backend.base.compute import Compute, NoCapacityError
from dstack.backend.base.storage import Storage
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.repo import RepoAddress
from dstack.core.request import RequestStatus
from dstack.core.runners import Runner
from dstack.utils.common import get_milliseconds_since_epoch


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
    storage.put_object(
        key=_get_job_filename(job.repo_address, job.job_id), content=yaml.dump(job.serialize())
    )


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
                job_id=job_id,
                repo_address=repo_address,
                run_name=run_name,
                workflow_name=workflow_name or None,
                provider_name=provider_name,
                local_repo_user_name=local_repo_user_name or None,
                status=JobStatus(status),
                submitted_at=int(submitted_at),
                artifact_paths=artifacts.split(",") if artifacts else None,
                tag_name=tag_name or None,
                app_names=app_names.split(",") or None,
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
                    job_id=job_id,
                    repo_address=repo_address,
                    run_name=run_name,
                    workflow_name=workflow_name or None,
                    provider_name=provider_name,
                    local_repo_user_name=local_repo_user_name,
                    status=JobStatus(status),
                    submitted_at=int(submitted_at),
                    artifact_paths=artifacts.split(",") if artifacts else None,
                    tag_name=tag_name or None,
                    app_names=app_names.split(",") or None,
                )
            )
    return job_heads


def delete_job_head(storage: Storage, repo_address: RepoAddress, job_id: str):
    job_head_key_prefix = _get_job_head_filename_prefix(repo_address, job_id)
    job_head_keys = storage.list_objects(job_head_key_prefix)
    for job_head_key in job_head_keys:
        storage.delete_object(job_head_key)


def run_job(
    storage: Storage,
    compute: Compute,
    job: Job,
    failed_to_start_job_new_status: JobStatus,
):
    if job.status != JobStatus.SUBMITTED:
        raise Exception("Can't create a request for a job which status is not SUBMITTED")

    runner = None
    try:
        job.runner_id = uuid.uuid4().hex
        update_job(storage, job)
        instance_type = compute.get_instance_type(job)
        if instance_type is None:
            job.status = JobStatus.FAILED
            update_job(storage, job)
            exit(f"No instance type matching requirements.")

        runner = Runner(
            runner_id=job.runner_id, request_id=None, resources=instance_type.resources, job=job
        )
        runners.create_runner(storage, runner)
        runner.request_id = compute.run_instance(job, instance_type)
        runners.update_runner(storage, runner)
    except NoCapacityError:
        job.status = failed_to_start_job_new_status
        job.request_id = runner.request_id if runner else None
        update_job(storage, job)
    except Exception as e:
        job.status = JobStatus.FAILED
        job.request_id = runner.request_id if runner else None
        update_job(storage, job)
        raise e


def stop_job(
    storage: Storage,
    compute: Compute,
    repo_address: RepoAddress,
    job_id: str,
    abort: bool,
):
    # TODO: why checking statuses of job_head, job, runner at the same time
    job_head = list_job_head(storage, repo_address, job_id)
    job = get_job(storage, repo_address, job_id)
    runner = runners.get_runner(storage, job.runner_id) if job else None
    request_status = (
        compute.get_request_head(
            job, (runner.request_id if runner else None) or job.request_id
        ).status
        if job
        else RequestStatus.TERMINATED
    )
    if (
        job_head
        and job_head.status.is_unfinished()
        or job
        and job.status.is_unfinished()
        or runner
        and runner.job.status.is_unfinished()
        or request_status != RequestStatus.TERMINATED
    ):
        if abort:
            new_status = JobStatus.ABORTED
        elif (
            not job_head
            or job_head.status in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]
            or not job
            or job.status in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]
            or request_status == RequestStatus.TERMINATED
            or not runner
        ):
            new_status = JobStatus.STOPPED
        elif (
            job_head
            and job_head.status != JobStatus.UPLOADING
            or job
            and job.status != JobStatus.UPLOADING
        ):
            new_status = JobStatus.STOPPING
        else:
            new_status = None
        if new_status:
            if runner and runner.job.status.is_unfinished() and runner.job.status != new_status:
                if new_status.is_finished():
                    runners.stop_runner(storage, compute, runner)
                else:
                    runner.job.status = new_status
                    runners.update_runner(storage, runner)
            if (
                job_head
                and job_head.status.is_unfinished()
                and job_head.status != new_status
                or job
                and job.status.is_unfinished()
                and job.status != new_status
            ):
                job.status = new_status
                update_job(storage, job)


def update_job_submission(job: Job):
    job.status = JobStatus.SUBMITTED
    job.submission_num += 1
    job.submitted_at = get_milliseconds_since_epoch()


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
    key = f"{prefix}l;{job_id};"
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
