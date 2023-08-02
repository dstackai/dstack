from typing import List, Optional, Tuple

import yaml
from pydantic import ValidationError

import dstack._internal.backend.base.gateway as gateway
from dstack._internal.backend.base import runners
from dstack._internal.backend.base.compute import Compute, InstanceNotFoundError, NoCapacityError
from dstack._internal.backend.base.secrets import SecretsManager
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.error import BackendError, BackendValueError, NoMatchingInstanceError
from dstack._internal.core.instance import InstanceType
from dstack._internal.core.job import (
    ConfigurationType,
    Job,
    JobErrorCode,
    JobHead,
    JobStatus,
    SpotPolicy,
    TerminationPolicy,
)
from dstack._internal.core.repo import RepoRef
from dstack._internal.core.runners import Runner
from dstack._internal.utils.common import get_milliseconds_since_epoch
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.escape import escape_head, unescape_head
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def create_job(
    storage: Storage,
    job: Job,
    create_head: bool = True,
):
    if create_head:
        storage.put_object(key=_get_job_head_filename_from_job(job), content="")

    storage.put_object(
        key=_get_job_filename(job.repo_ref.repo_id, job.job_id), content=yaml.dump(job.serialize())
    )


def get_job(storage: Storage, repo_id: str, job_id: str) -> Optional[Job]:
    obj = storage.get_object(_get_job_filename(repo_id, job_id))
    if obj is None:
        return None
    try:
        job = Job.unserialize(yaml.load(obj, yaml.FullLoader))
    except ValidationError:
        return None
    return job


def update_job(storage: Storage, job: Job):
    job_head_key_prefix = _get_job_head_filename_prefix(job.repo_ref.repo_id, job.job_id)
    job_keys = storage.list_objects(job_head_key_prefix)
    for key in job_keys:
        storage.delete_object(key)
    storage.put_object(key=_get_job_head_filename_from_job(job), content="")
    storage.put_object(
        key=_get_job_filename(job.repo_ref.repo_id, job.job_id), content=yaml.dump(job.serialize())
    )


def list_jobs(storage: Storage, repo_id: str, run_name: str) -> List[Job]:
    job_key_run_prefix = _get_jobs_filenames_prefix(repo_id, run_name)
    jobs_keys = storage.list_objects(job_key_run_prefix)
    jobs = []
    for job_key in jobs_keys:
        job_obj = storage.get_object(job_key)
        job = Job.unserialize(yaml.load(job_obj, yaml.FullLoader))
        jobs.append(job)
    return jobs


def get_job_head(storage: Storage, repo_id: str, job_id: str) -> Optional[JobHead]:
    job_head_key_prefix = _get_job_head_filename_prefix(repo_id, job_id)
    job_head_keys = storage.list_objects(job_head_key_prefix)
    for job_head_key in job_head_keys:
        return _parse_job_head_key(repo_id, job_head_key)
    return None


def list_job_heads(
    storage: Storage,
    repo_id: str,
    run_name: Optional[str] = None,
) -> List[JobHead]:
    job_heads_keys_prefix = _get_job_heads_filenames_prefix(repo_id, run_name)
    job_heads_keys = storage.list_objects(job_heads_keys_prefix)
    job_heads = []
    for job_head_key in job_heads_keys:
        job_heads.append(_parse_job_head_key(repo_id, job_head_key))
    return job_heads


def delete_job_head(storage: Storage, repo_id: str, job_id: str):
    job_head_key_prefix = _get_job_head_filename_prefix(repo_id, job_id)
    job_head_keys = storage.list_objects(job_head_key_prefix)
    for job_head_key in job_head_keys:
        storage.delete_object(job_head_key)


def delete_jobs(storage: Storage, repo_id: str, run_name: str):
    job_key_run_prefix = _get_jobs_filenames_prefix(repo_id, run_name)
    jobs_keys = storage.list_objects(job_key_run_prefix)
    for job_key in jobs_keys:
        storage.delete_object(job_key)


def predict_job_instance(
    compute: Compute,
    job: Job,
) -> Optional[InstanceType]:
    return compute.get_instance_type(job)


def run_job(
    storage: Storage,
    compute: Compute,
    secrets_manager: SecretsManager,
    job: Job,
    failed_to_start_job_new_status: JobStatus,
):
    if job.status != JobStatus.SUBMITTED:
        raise BackendError("Can't create a request for a job which status is not SUBMITTED")
    try:
        if job.configuration_type == ConfigurationType.SERVICE:
            job.gateway.hostname = gateway.resolve_hostname(
                secrets_manager, job.repo_ref.repo_id, job.gateway.hostname
            )
            private_bytes, public_bytes = generate_rsa_key_pair_bytes(comment=job.run_name)
            job.gateway.sock_path = gateway.publish(
                job.gateway.hostname, job.gateway.public_port, public_bytes
            )
            job.gateway.ssh_key = private_bytes.decode()
            update_job(storage, job)

        _try_run_job(
            storage=storage,
            compute=compute,
            job=job,
            failed_to_start_job_new_status=failed_to_start_job_new_status,
        )
    except Exception as e:
        job.status = JobStatus.FAILED
        update_job(storage, job)
        raise e


def restart_job(
    storage: Storage,
    compute: Compute,
    job: Job,
):
    logger.info("Restarting job [repo_id=%s job_id=%s]", job.repo.repo_id, job.job_id)
    if job.status != JobStatus.STOPPED:
        raise BackendValueError("Cannot restart job which status is not stopped")
    runner = runners.get_runner(storage, job.runner_id)
    try:
        launched_instance_info = compute.restart_instance(job)
    except InstanceNotFoundError:
        raise BackendValueError("Instance not found")
    job.submitted_at = get_milliseconds_since_epoch()
    job.status = JobStatus.RESTARTING
    job.request_id = runner.request_id = launched_instance_info.request_id
    runners.update_runner(storage, runner)
    update_job(storage, job)


def stop_job(
    storage: Storage, compute: Compute, repo_id: str, job_id: str, terminate: bool, abort: bool
):
    logger.info("Stopping job [repo_id=%s job_id=%s]", repo_id, job_id)
    job_head = get_job_head(storage, repo_id, job_id)
    if job_head.status.is_finished() and not job_head.status == JobStatus.STOPPED:
        return
    job = get_job(storage, repo_id, job_id)
    if job is not None and job.termination_policy == TerminationPolicy.TERMINATE:
        terminate = True
    if job_head.status.is_finished() and not terminate:
        return
    new_status = None
    if abort:
        new_status = JobStatus.ABORTED
    elif job_head.status in [
        JobStatus.SUBMITTED,
        JobStatus.RESTARTING,
        JobStatus.DOWNLOADING,
        JobStatus.STOPPED,
    ]:
        if terminate:
            new_status = JobStatus.TERMINATED
        else:
            new_status = JobStatus.STOPPED
    elif job_head.status in [JobStatus.BUILDING, JobStatus.RUNNING]:
        if terminate:
            new_status = JobStatus.TERMINATING
        else:
            new_status = JobStatus.STOPPING
    if new_status is not None and new_status != job_head.status:
        if job is not None:
            job.status = new_status
            update_job(storage, job)
            runner = runners.get_runner(storage, job.runner_id)
            if new_status in [JobStatus.TERMINATED, JobStatus.ABORTED]:
                if runner is not None:
                    runners.terminate_runner(compute, runner)
        else:
            # If job file is deleted/corrupted, we'll update the job head only.
            job_head.status = new_status
            _update_job_head(storage, job_head)


def update_job_submission(job: Job):
    job.status = JobStatus.SUBMITTED
    job.submission_num += 1
    job.submitted_at = get_milliseconds_since_epoch()


def _try_run_job(
    storage: Storage,
    compute: Compute,
    job: Job,
    failed_to_start_job_new_status: JobStatus,
    attempt: int = 0,
):
    spot = (
        job.spot_policy is SpotPolicy.SPOT or job.spot_policy is SpotPolicy.AUTO and attempt == 0
    )
    job.requirements.spot = spot
    instance_type = compute.get_instance_type(job)
    if instance_type is None:
        if job.spot_policy == SpotPolicy.AUTO and attempt == 0:
            return _try_run_job(
                storage=storage,
                compute=compute,
                job=job,
                failed_to_start_job_new_status=failed_to_start_job_new_status,
                attempt=attempt + 1,
            )
        else:
            job.status = JobStatus.FAILED
            job.error_code = JobErrorCode.NO_INSTANCE_MATCHING_REQUIREMENTS
            update_job(storage, job)
            raise NoMatchingInstanceError()
    job.instance_type = instance_type.instance_name
    update_job(storage, job)
    runner = Runner(
        runner_id=job.runner_id, request_id=None, resources=instance_type.resources, job=job
    )
    runners.create_runner(storage, runner)
    try:
        launched_instance_info = compute.run_instance(job, instance_type)
        runner.request_id = job.request_id = launched_instance_info.request_id
        job.location = launched_instance_info.location
    except NoCapacityError:
        if job.spot_policy == SpotPolicy.AUTO and attempt == 0:
            return _try_run_job(
                storage=storage,
                compute=compute,
                job=job,
                failed_to_start_job_new_status=failed_to_start_job_new_status,
                attempt=attempt + 1,
            )
        else:
            job.status = failed_to_start_job_new_status
            job.error_code = JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY
            update_job(storage, job)
    else:
        runners.update_runner(storage, runner)
        update_job(storage, job)


def _update_job_head(storage: Storage, job_head: JobHead):
    job_head_key_prefix = _get_job_head_filename_prefix(job_head.repo_ref.repo_id, job_head.job_id)
    job_keys = storage.list_objects(job_head_key_prefix)
    for key in job_keys:
        storage.delete_object(key)
    storage.put_object(key=_get_job_head_filename_from_job_head(job_head), content="")


def _get_jobs_dir(repo_id: str) -> str:
    return f"jobs/{repo_id}/"


def _get_job_filename(repo_id: str, job_id: str) -> str:
    return f"{_get_jobs_dir(repo_id)}{job_id}.yaml"


def _get_jobs_filenames_prefix(repo_id: str, run_name: str) -> str:
    return f"{_get_jobs_dir(repo_id)}{run_name},"


def _get_job_heads_filenames_prefix(repo_id: str, run_name: Optional[str]) -> str:
    return f"{_get_jobs_dir(repo_id)}l;{run_name or ''}"


def _get_job_head_filename_prefix(repo_id: str, job_id: str) -> str:
    prefix = _get_jobs_dir(repo_id)
    key = f"{prefix}l;{job_id};"
    return key


def _get_job_head_filename_from_job(job: Job) -> str:
    prefix = _get_jobs_dir(job.repo_ref.repo_id)
    key = (
        f"{prefix}l;"
        f"{job.job_id};"
        f"{job.provider_name};"
        f"{job.hub_user_name};"
        f"{job.submitted_at};"
        f"{job.status.value},{job.error_code.value if job.error_code else ''},{job.container_exit_code or ''};"
        f"{','.join([escape_head(a.artifact_path) for a in (job.artifact_specs or [])])};"
        f"{','.join([a.app_name for a in (job.app_specs or [])])};"
        f"{job.tag_name or ''};"
        f"{job.instance_type or ''};"
        f"{escape_head(job.configuration_path)};"
        f"{job.get_instance_spot_type()}"
    )
    return key


def _get_job_head_filename_from_job_head(job_head: JobHead) -> str:
    prefix = _get_jobs_dir(job_head.repo_ref.repo_id)
    key = (
        f"{prefix}l;"
        f"{job_head.job_id};"
        f"{job_head.provider_name};"
        f"{job_head.hub_user_name};"
        f"{job_head.submitted_at};"
        f"{job_head.status.value},{job_head.error_code.value if job_head.error_code else ''},{job_head.container_exit_code or ''};"
        f"{','.join([escape_head(artifact_path) for artifact_path in (job_head.artifact_paths or [])])};"
        f"{','.join([app_name for app_name in (job_head.app_names or [])])};"
        f"{job_head.tag_name or ''};"
        f"{job_head.instance_type or ''};"
        f"{escape_head(job_head.configuration_path)};"
        f"{job_head.instance_spot_type}"
    )
    return key


def _parse_job_head_key(repo_id: str, full_key: str) -> JobHead:
    tokens = full_key[len(_get_jobs_dir(repo_id)) :].split(";")
    tokens.extend([""] * (12 - len(tokens)))  # pad with empty tokens
    (
        _,
        job_id,
        provider_name,
        hub_user_name,
        submitted_at,
        status_info,
        artifacts,
        app_names,
        tag_name,
        instance_type,
        configuration_path,
        instance_spot_type,
    ) = tokens
    run_name, workflow_name, job_index = tuple(job_id.split(","))
    status, error_code, container_exit_code = _parse_job_status_info(status_info)
    return JobHead(
        job_id=job_id,
        repo_ref=RepoRef(repo_id=repo_id),
        hub_user_name=hub_user_name,
        run_name=run_name,
        workflow_name=workflow_name or None,
        provider_name=provider_name,
        status=JobStatus(status),
        error_code=JobErrorCode(error_code) if error_code else None,
        container_exit_code=int(container_exit_code) if container_exit_code else None,
        submitted_at=int(submitted_at),
        artifact_paths=[unescape_head(path) for path in artifacts.split(",")]
        if artifacts
        else None,
        tag_name=tag_name or None,
        app_names=app_names.split(",") or None,
        instance_type=instance_type or None,
        configuration_path=unescape_head(configuration_path),
        instance_spot_type=instance_spot_type or None,
    )


def _parse_job_status_info(status_info: str) -> Tuple[str, str, str]:
    if len(status_info.split(",")) == 3:
        return status_info.split(",")
    return status_info, "", ""
