from typing import List, Optional

import yaml
from google.cloud.storage import Bucket

from dstack.backend.gcp import runners, storage
from dstack.backend.gcp.config import GCPConfig
from dstack.core.instance import InstanceType
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.repo import RepoAddress
from dstack.core.runners import Resources, Runner


def create_job(bucket: Bucket, job: Job):
    counter = 0
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter}"
    job.set_id(job_id)
    prefix = f"jobs/{job.repo_address.path()}"
    key = f"{prefix}/{job_id}.yaml"
    storage.put_object(bucket, key, yaml.dump(job.serialize()))
    storage.put_object(bucket, job.job_head_key(), "")


def get_job(bucket: Bucket, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
    prefix = f"jobs/{job.repo_address.path()}"
    key = f"{prefix}/{job_id}.yaml"
    obj = storage.read_object(bucket, key)
    job = Job.unserialize(yaml.load(obj, yaml.FullLoader))
    return job


def update_job(bucket: Bucket, job: Job):
    delete_job_head(bucket, job.repo_address, job.job_id)
    create_job(bucket, job)


def delete_job_head(bucket: Bucket, repo_address: RepoAddress, job_id: str):
    jobs_prefix = f"jobs/{repo_address.path()}"
    job_head_key_prefix = f"{jobs_prefix}/l;{job_id};"
    object_names = storage.list_objects(bucket, prefix=job_head_key_prefix)
    for object_name in object_names:
        storage.delete_object(bucket, object_name)


def list_job_heads(
    bucket: Bucket, repo_address: RepoAddress, run_name: Optional[str] = None
) -> List[JobHead]:
    jobs_prefix = f"jobs/{repo_address.path()}"
    job_head_key_prefix = f"{jobs_prefix}/l;"
    job_head_key_run_prefix = job_head_key_prefix + run_name if run_name else job_head_key_prefix
    object_names = storage.list_objects(bucket, prefix=job_head_key_run_prefix)
    job_heads = []
    for object_name in object_names:
        t = object_name.split(";")
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
        ) = t
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


def run_job(gcp_config: GCPConfig, bucket: Bucket, job: Job):
    instance_type = _get_instance_type(job)
    runner = Runner(job.runner_id, None, instance_type.resources, job)
    runners.create_runner(bucket, runner)
    # We save request_id (aka instance name) but we can infer it from the job/runner
    runner.request_id = runners.launch_runner(gcp_config, bucket, runner)
    job.request_id = runner.request_id
    runners.update_runner(bucket, runner)
    update_job(bucket, job)


def _get_instance_type(job: Job) -> InstanceType:
    return InstanceType(
        instance_name="n1-standard-1",
        resources=Resources(cpus=1, memory_mib=3750, gpus=[], interruptible=False, local=False),
    )


def stop_job(
    gcp_config: GCPConfig, bucket: Bucket, repo_address: RepoAddress, job_id: str, abort: bool
):
    job = get_job(bucket, repo_address, job_id)
    if job.status.is_finished():
        return
    # TODO: proper, graceful stopping
    # Update runner instead of stop if Stopping
    runner = runners.get_runner(bucket, job.runner_id)
    runners.stop_runner(gcp_config, runner)
    job.status = JobStatus.STOPPED
    update_job(bucket, job)
    runners.delete_runner(bucket, job.runner_id)
