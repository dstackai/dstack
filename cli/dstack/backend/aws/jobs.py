from typing import List, Optional, Dict, Any

import yaml
from botocore.client import BaseClient

from dstack.core.job import Job, JobStatus, JobHead
from dstack.core.repo import RepoAddress


def create_job(
    s3_client: BaseClient,
    bucket_name: str,
    job: Job,
    counter: List[int] = [],
    create_head: bool = True,
):
    if len(counter) == 0:
        counter.append(0)
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
    job.set_id(job_id)
    if create_head:
        s3_client.put_object(Body="", Bucket=bucket_name, Key=job.job_head_key())
    prefix = f"jobs/{job.repo_data.path()}"
    key = f"{prefix}/{job_id}.yaml"
    s3_client.put_object(Body=yaml.dump(job.serialize()), Bucket=bucket_name, Key=key)
    counter[0] += 1


def store_job(
    s3_client: BaseClient,
    bucket_name: str,
    job: Job,
):
    create_job(s3_client, bucket_name, job)


def get_job(
    s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, job_id: str
) -> Optional[Job]:
    prefix = f"jobs/{repo_address.path()}"
    key = f"{prefix}/{job_id}.yaml"
    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=key)
        job = Job.unserialize(yaml.load(obj["Body"].read().decode("utf-8"), yaml.FullLoader))
        return job
    except Exception as e:
        if (
            hasattr(e, "response")
            and e.response.get("Error")
            and e.response["Error"].get("Code") == "NoSuchKey"
        ):
            return None
        else:
            raise e


def update_job(s3_client: BaseClient, bucket_name: str, job: Job):
    prefix = f"jobs/{job.repo_data.path()}"
    job_head_key_prefix = f"{prefix}/l;{job.job_id};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response["Contents"]:
        s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    job_head_key = job.job_head_key()
    s3_client.put_object(Body="", Bucket=bucket_name, Key=job_head_key)
    key = f"{prefix}/{job.job_id}.yaml"
    s3_client.put_object(Body=yaml.dump(job.serialize()), Bucket=bucket_name, Key=key)


def list_job_heads(
    s3_client: BaseClient,
    bucket_name: str,
    repo_address: RepoAddress,
    run_name: Optional[str] = None,
) -> List[JobHead]:
    prefix = f"jobs/{repo_address.path()}"
    job_head_key_prefix = f"{prefix}/l;"
    job_head_key_run_prefix = job_head_key_prefix + run_name if run_name else job_head_key_prefix
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_run_prefix)
    job_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            t = obj["Key"][len(job_head_key_prefix) :].split(";")
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


def list_job_head(
    s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, job_id: str
) -> Optional[JobHead]:
    prefix = f"jobs/{repo_address.path()}"
    job_head_key_prefix = f"{prefix}/l;{job_id};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_prefix)
    if "Contents" in response:
        for obj in response["Contents"]:
            t = obj["Key"][len(job_head_key_prefix) :].split(";")
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


def list_jobs(
    s3_client: BaseClient,
    bucket_name: str,
    repo_address: RepoAddress,
    run_name: Optional[str] = None,
) -> List[Job]:
    job_key_run_prefix = f"jobs/{repo_address.path()}/{run_name},"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_key_run_prefix)
    jobs = []
    if "Contents" in response:
        for obj in response["Contents"]:
            job_obj = s3_client.get_object(Bucket=bucket_name, Key=obj["Key"])
            job = Job.unserialize(
                yaml.load(job_obj["Body"].read().decode("utf-8"), yaml.FullLoader)
            )
            jobs.append(job)
    return jobs


def delete_job_head(
    s3_client: BaseClient, bucket_name: str, repo_address: RepoAddress, job_id: str
):
    prefix = f"jobs/{repo_address.path()}"
    job_head_key_prefix = f"{prefix}/l;{job_id};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response["Contents"]:
        s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
