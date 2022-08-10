from typing import List, Optional

import yaml
from botocore.client import BaseClient

from dstack.jobs import Job, JobStatus, JobHead, Requirements, GpusRequirements, JobRefId, JobApp
from dstack.repo import Repo


def serialize_job(job: Job) -> dict:
    previous_job_ids = []
    if job.previous_jobs:
        for j in job.previous_jobs:
            previous_job_ids.append(j.get_id())
    requirements = None
    if job.requirements:
        requirements = {}
        if job.requirements.cpus:
            requirements["cpus"] = {
                "count": job.requirements.cpus
            }
        if job.requirements.memory_mib:
            requirements["memory_mib"] = job.requirements.memory_mib
        if job.requirements.gpus:
            requirements["gpus"] = {
                "count": job.requirements.gpus.count
            }
            if job.requirements.gpus.memory_mib:
                requirements["gpus"]["memory_mib"] = job.requirements.gpus.memory_mib
            if job.requirements.gpus.name:
                requirements["gpus"]["name"] = job.requirements.gpus.name
        if job.requirements.shm_size:
            requirements["shm_size"] = job.requirements.shm_size
        if job.requirements.interruptible:
            requirements["interruptible"] = job.requirements.interruptible
    job_data = {
        "job_id": job.get_id(),
        "repo_user_name": job.repo.repo_user_name,
        "repo_name": job.repo.repo_name,
        "repo_branch": job.repo.repo_branch,
        "repo_hash": job.repo.repo_hash,
        "repo_diff": job.repo.repo_diff or '',
        "run_name": job.run_name,
        "workflow_name": job.workflow_name or '',
        "provider_name": job.provider_name,
        "status": job.status.value,
        "submitted_at": job.submitted_at,
        "image_name": job.image_name,
        "commands": job.commands or [],
        "env": job.env or {},
        "working_dir": job.working_dir or '',
        "artifacts": job.artifacts or [],
        "port_count": job.port_count if job.port_count else 0,
        "ports": [str(port) for port in job.ports] if job.ports else [],
        "host_name": job.host_name or '',
        "requirements": requirements or {},
        "previous_job_ids": previous_job_ids or [],
        "master_job_id": job.master_job.get_id() if job.master_job else '',
        "apps": [{
            "port_index": app.port_index,
            "app_name": app.app_name,
            "url_path": app.url_path or '',
            "url_query_params": app.url_query_params or '',
        } for app in job.apps] if job.apps else [],
        "runner_id": job.runner_id or '',
        "tag_name": job.tag_name or '',
    }
    return job_data


def unserialize_job(job_data: dict) -> Job:
    requirements = Requirements(
        job_data["requirements"].get("cpu") or None,
        job_data["requirements"].get("memory") or None,
        GpusRequirements(job_data["requirements"]["gpu"].get("count") or None,
                         job_data["requirements"]["gpu"].get("memory") or None,
                         job_data["requirements"]["gpu"].get("name") or None
                         ) if job_data["requirements"].get("gpu") else None,
        job_data.get("shm_size") or None, job_data.get("interruptible") or None
    ) if job_data.get("requirements") else None
    if requirements:
        if not requirements.cpus \
                and (not requirements.gpus or
                     (not requirements.gpus.count
                      and not requirements.gpus.memory_mib
                      and not requirements.gpus.name)) \
                and not requirements.interruptible and not not requirements.shm_size:
            requirements = None
    previous_jobs = ([JobRefId(p) for p in (job_data["previous_job_ids"] or [])]) or None
    master_job = JobRefId(job_data["master_job_id"]) if job_data.get("master_job_id") else None
    apps = ([JobApp(a["port_index"], a["app_name"], a.get("url_path") or None, a.get("url_query_params") or None) for a
             in (job_data["apps"] or [])]) or None
    job = Job(Repo(job_data["repo_user_name"], job_data["repo_name"], job_data["repo_branch"], job_data["repo_hash"],
                   job_data["repo_diff"] or None),
              job_data["run_name"], job_data.get("workflow_name") or None, job_data["provider_name"],
              JobStatus(job_data["status"]), job_data["submitted_at"], job_data["image_name"],
              job_data.get("commands") or None,
              job_data["env"] or None, job_data.get("working_dir") or None, job_data.get("artifacts") or None,
              job_data.get("port_count") or None, job_data.get("ports") or None, job_data.get("host_name") or None,
              requirements, previous_jobs, master_job, apps, job_data.get("runner_id") or None,
              job_data.get("tag_name"))
    if "job_id" in job_data:
        job.set_id(job_data["job_id"])
    return job


def _l_key(job: Job):
    prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
    lKey = f"{prefix}/l;{job.get_id()};" \
           f"{job.provider_name};{job.submitted_at};{job.status.value};" \
           f"{job.runner_id or ''};{','.join(job.artifacts or [])};" \
           f"{','.join(map(lambda a: a.app_name, job.apps or []))};{job.tag_name or ''}"
    return lKey


def create_job(s3_client: BaseClient, bucket_name: str, job: Job, counter: List[int] = [], listed: bool = True):
    if len(counter) == 0:
        counter.append(0)
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
    job.set_id(job_id)
    if listed:
        lKey = _l_key(job)
        s3_client.put_object(Body="", Bucket=bucket_name, Key=lKey)
    prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
    key = f"{prefix}/{job_id}.yaml"
    s3_client.put_object(Body=yaml.dump(serialize_job(job)), Bucket=bucket_name, Key=key)
    counter[0] += 1


def get_job(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str) -> Job:
    prefix = f"jobs/{repo_user_name}/{repo_name}"
    key = f"{prefix}/{job_id}.yaml"
    obj = s3_client.get_object(Bucket=bucket_name, Key=key)
    job = unserialize_job(yaml.load(obj['Body'].read().decode('utf-8'), yaml.FullLoader))
    job.set_id(job_id)
    return job


def update_job(s3_client: BaseClient, bucket_name: str, job: Job):
    prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
    lKeyPrefix = f"{prefix}/l;{job.get_id()};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=lKeyPrefix, MaxKeys=1)
    for obj in response["Contents"]:
        s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    lKey = _l_key(job)
    s3_client.put_object(Body="", Bucket=bucket_name, Key=lKey)
    key = f"{prefix}/{job.get_id()}.yaml"
    s3_client.put_object(Body=yaml.dump(serialize_job(job)), Bucket=bucket_name, Key=key)


def get_job_heads(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                  run_name: Optional[str] = None):
    prefix = f"jobs/{repo_user_name}/{repo_name}"
    lKeyPrefix = f"{prefix}/l;"
    lKeyRunPrefix = lKeyPrefix + run_name if run_name else lKeyPrefix
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=lKeyRunPrefix)
    job_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            job_id, provider_name, submitted_at, status, runner_id, artifacts, apps, tag_name = tuple(
                obj["Key"][len(lKeyPrefix):].split(';'))
            run_name, workflow_name, job_index = tuple(job_id.split(','))
            job_heads.append(JobHead(repo_user_name, repo_name,
                                     job_id, run_name, workflow_name or None, provider_name,
                                     JobStatus(status), int(submitted_at), runner_id or None,
                                     artifacts.split(',') if artifacts else None, tag_name or None))
    return job_heads
