from typing import List, Optional, Dict, Any

import yaml
from botocore.client import BaseClient

from dstack.jobs import Job, JobStatus, JobHead, Requirements, GpusRequirements, JobRefId, AppSpec, Dep
from dstack.repo import RepoData


def serialize_job(job: Job) -> dict:
    deps = []
    if job.deps:
        for dep in job.deps:
            deps.append(f"{dep.repo_user_name},{dep.repo_name},{dep.run_name}")
    job_data = {
        "job_id": job.job_id,
        "repo_user_name": job.repo_data.repo_user_name,
        "repo_name": job.repo_data.repo_name,
        "repo_branch": job.repo_data.repo_branch,
        "repo_hash": job.repo_data.repo_hash,
        "repo_diff": job.repo_data.repo_diff or '',
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
        "requirements": _serialize_requirements(job.requirements),
        "deps": deps,
        "master_job_id": job.master_job.get_id() if job.master_job else '',
        "apps": [{
            "port_index": a.port_index,
            "app_name": a.app_name,
            "url_path": a.url_path or '',
            "url_query_params": a.url_query_params or '',
        } for a in job.app_specs] if job.app_specs else [],
        "runner_id": job.runner_id or '',
        "request_id": job.request_id or '',
        "tag_name": job.tag_name or '',
    }
    return job_data


def _serialize_requirements(requirements) -> Dict[str, Any]:
    req_data = {}
    if requirements:
        if requirements.cpus:
            req_data["cpus"] = {
                "count": requirements.cpus
            }
        if requirements.memory_mib:
            req_data["memory_mib"] = requirements.memory_mib
        if requirements.gpus:
            req_data["gpus"] = {
                "count": requirements.gpus.count
            }
            if requirements.gpus.memory_mib:
                req_data["gpus"]["memory_mib"] = requirements.gpus.memory_mib
            if requirements.gpus.name:
                req_data["gpus"]["name"] = requirements.gpus.name
        if requirements.shm_size:
            req_data["shm_size"] = requirements.shm_size
        if requirements.interruptible:
            req_data["interruptible"] = requirements.interruptible
    return req_data


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
    deps = []
    if job_data.get("deps"):
        for dep in job_data["deps"]:
            dep_repo_user_name, dep_repo_name, dep_run_name = tuple(dep.split(","))
            deps.append(Dep(dep_repo_user_name, dep_repo_name, dep_run_name))
    master_job = JobRefId(job_data["master_job_id"]) if job_data.get("master_job_id") else None
    app_specs = ([AppSpec(a["port_index"], a["app_name"], a.get("url_path") or None, a.get("url_query_params") or None)
                  for a in (job_data.get("apps") or [])]) or None
    job = Job(job_data.get("job_id"), RepoData(job_data["repo_user_name"], job_data["repo_name"],
                                               job_data["repo_branch"], job_data["repo_hash"],
                                               job_data["repo_diff"] or None),
              job_data["run_name"], job_data.get("workflow_name") or None, job_data["provider_name"],
              JobStatus(job_data["status"]), job_data["submitted_at"], job_data["image_name"],
              job_data.get("commands") or None, job_data["env"] or None, job_data.get("working_dir") or None,
              job_data.get("artifacts") or None, job_data.get("port_count") or None, job_data.get("ports") or None,
              job_data.get("host_name") or None, requirements, deps or None, master_job, app_specs,
              job_data.get("runner_id") or None, job_data.get("request_id") or None, job_data.get("tag_name") or None)
    return job


def _job_head_key(job: Job):
    prefix = f"jobs/{job.repo_data.repo_user_name}/{job.repo_data.repo_name}"
    key = f"{prefix}/l;" \
          f"{job.job_id};" \
          f"{job.provider_name};" \
          f"{job.submitted_at};" \
          f"{job.status.value};" \
          f"{','.join(job.artifacts or [])};" \
          f"{','.join(map(lambda a: a.app_name, job.app_specs or []))};{job.tag_name or ''}"
    return key


def create_job(s3_client: BaseClient, bucket_name: str, job: Job, counter: List[int] = [], create_head: bool = True):
    if len(counter) == 0:
        counter.append(0)
    job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
    job.set_id(job_id)
    if create_head:
        s3_client.put_object(Body="", Bucket=bucket_name, Key=_job_head_key(job))
    prefix = f"jobs/{job.repo_data.repo_user_name}/{job.repo_data.repo_name}"
    key = f"{prefix}/{job_id}.yaml"
    s3_client.put_object(Body=yaml.dump(serialize_job(job)), Bucket=bucket_name, Key=key)
    counter[0] += 1


def get_job(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str) -> Optional[Job]:
    prefix = f"jobs/{repo_user_name}/{repo_name}"
    key = f"{prefix}/{job_id}.yaml"
    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=key)
        job = unserialize_job(yaml.load(obj['Body'].read().decode('utf-8'), yaml.FullLoader))
        job.set_id(job_id)
        return job
    except Exception as e:
        if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchKey":
            return None
        else:
            raise e


def update_job(s3_client: BaseClient, bucket_name: str, job: Job):
    prefix = f"jobs/{job.repo_data.repo_user_name}/{job.repo_data.repo_name}"
    job_head_key_prefix = f"{prefix}/l;{job.job_id};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response["Contents"]:
        s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
    job_head_key = _job_head_key(job)
    s3_client.put_object(Body="", Bucket=bucket_name, Key=job_head_key)
    key = f"{prefix}/{job.job_id}.yaml"
    s3_client.put_object(Body=yaml.dump(serialize_job(job)), Bucket=bucket_name, Key=key)


def list_job_heads(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str,
                   run_name: Optional[str] = None):
    prefix = f"jobs/{repo_user_name}/{repo_name}"
    job_head_key_prefix = f"{prefix}/l;"
    job_head_key_run_prefix = job_head_key_prefix + run_name if run_name else job_head_key_prefix
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_run_prefix)
    job_heads = []
    if "Contents" in response:
        for obj in response["Contents"]:
            job_id, provider_name, submitted_at, status, artifacts, app_names, tag_name = tuple(
                obj["Key"][len(job_head_key_prefix):].split(';'))
            run_name, workflow_name, job_index = tuple(job_id.split(','))
            job_heads.append(JobHead(job_id, repo_user_name, repo_name, run_name, workflow_name or None, provider_name,
                                     JobStatus(status), int(submitted_at),
                                     artifacts.split(',') if artifacts else None, tag_name or None,
                                     app_names or None))
    return job_heads


def delete_job_head(s3_client: BaseClient, bucket_name: str, repo_user_name: str, repo_name: str, job_id: str):
    prefix = f"jobs/{repo_user_name}/{repo_name}"
    job_head_key_prefix = f"{prefix}/l;{job_id};"
    response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=job_head_key_prefix, MaxKeys=1)
    for obj in response["Contents"]:
        s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
