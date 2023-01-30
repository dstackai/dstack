from typing import Optional, List

from google.cloud.storage import Bucket
import yaml

from dstack.core.instance import InstanceType
from dstack.backend import Job, JobHead, RepoAddress
from dstack.core.job import JobStatus
from dstack.core.repo import _repo_address_path
from dstack.core.runners import Resources, Runner
from dstack.backend.aws.jobs import serialize_job, _job_head_key, unserialize_job
from dstack.backend.gcp import runners, storage
from dstack.backend.gcp.config import GCPConfig


def create_job(bucket: Bucket, job: Job):
    counter = 0
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter}"
    job.set_id(job_id)
    prefix = f"jobs/{_repo_address_path(job.repo_address)}"
    key = f"{prefix}/{job_id}.yaml"
    storage.put_object(bucket, key, yaml.dump(serialize_job(job)))
    storage.put_object(bucket, _job_head_key(job), '')


def run_job(gcp_config: GCPConfig, bucket: Bucket, job: Job):
    instance_type = _get_instance_type(job)
    runner = Runner(job.runner_id, None, instance_type.resources, job)
    runners.create_runner(bucket, runner)
    runners.launch_runner(gcp_config, bucket, runner)


def _get_instance_type(job: Job) -> InstanceType:
    return InstanceType(
        instance_name="n1-standard-1",
        resources=Resources(cpus=1, memory_mib=3750, gpus=[], interruptible=False, local=False),
    )


def list_job_heads(bucket: Bucket, repo_address: RepoAddress, run_name: Optional[str] = None) -> List[JobHead]:
    jobs_prefix = f"jobs/{_repo_address_path(repo_address)}"
    job_head_key_prefix = f"{jobs_prefix}/l;"
    job_head_key_run_prefix = job_head_key_prefix + run_name if run_name else job_head_key_prefix
    # TODO pagination
    blobs = bucket.client.list_blobs(bucket.name, prefix=job_head_key_run_prefix)
    job_heads = []
    for blob in blobs:
        t = blob.name.split(";")
        _, job_id, provider_name, local_repo_user_name, submitted_at, status, artifacts, app_names, tag_name = t
        run_name, workflow_name, job_index = tuple(job_id.split(','))
        job_heads.append(JobHead(job_id, repo_address, run_name, workflow_name or None, provider_name,
                                    local_repo_user_name, JobStatus(status), int(submitted_at),
                                    artifacts.split(',') if artifacts else None, tag_name or None,
                                    app_names.split(',') or None))
    return job_heads


def get_job(bucket: Bucket, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
    prefix = f"jobs/{_repo_address_path(repo_address)}"
    key = f"{prefix}/{job_id}.yaml"
    obj = storage.read_object(bucket, key)
    job = unserialize_job(yaml.load(obj, yaml.FullLoader))
    return job
