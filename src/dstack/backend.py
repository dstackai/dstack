import time
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional

import boto3
import yaml
from botocore.client import BaseClient
from yaml import dump

from dstack import random_name, Job, Repo, JobStatus, JobRef, JobRefId, App, Requirements, GpusRequirements, JobHead, \
    Runner, Resources
from dstack.config import load_config, AwsBackendConfig


class Backend(ABC):
    @abstractmethod
    def next_run_name(self):
        pass

    # noinspection PyDefaultArgument
    @abstractmethod
    def create_job(self, job: Job, counter: List[int] = []):
        pass

    @abstractmethod
    def update_job(self, job: Job):
        pass

    @abstractmethod
    def get_job(self, repo_user_name: str, repo_name: str, job_id: str) -> Job:
        pass

    @abstractmethod
    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None):
        pass

    @abstractmethod
    def create_runner(self, runner_state: Runner):
        pass


class AwsBackend(Backend):
    def __init__(self, config: AwsBackendConfig):
        self.config = config

    def __s3_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.config.profile_name, region_name=self.config.region_name)
        return session.client("s3")

    def next_run_name(self):
        name = random_name.next_name()
        client = self.__s3_client()
        count = 0
        key = f"run-names/{name}.yaml"
        try:
            obj = client.get_object(Bucket=self.config.bucket_name, Key=key)
            count = yaml.load(obj['Body'].read().decode('utf-8'), Loader=yaml.FullLoader)["count"]
            client.put_object(Body=dump({"count": count + 1}), Bucket=self.config.bucket_name, Key=key)
        except Exception as e:
            # noinspection PyUnresolvedReferences
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchKey":
                client.put_object(Body=dump({"count": count + 1}), Bucket=self.config.bucket_name, Key=key)
            else:
                raise e
        return f"{name}-{count + 1}"

    @staticmethod
    def _serialize_job(job: Job) -> dict:
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
            "variables": job.variables or {},
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

    @staticmethod
    def _unserialize_job(job_data: dict) -> Job:
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
        apps = ([App(a["app_name"], a["port_index"], a.get("url_path") or None, a.get("url_query_params") or None) for a
                 in (job_data["apps"] or [])]) or None
        return Job(Repo(job_data["repo_user_name"], job_data["repo_name"],
                        job_data["repo_branch"], job_data["repo_hash"], job_data["repo_diff"] or None),
                   job_data["run_name"], job_data.get("workflow_name") or None,
                   job_data["provider_name"], JobStatus(job_data["status"]),
                   job_data["submitted_at"], job_data["image_name"],
                   job_data.get("commands") or None, job_data.get("variables") or None, job_data["env"] or None,
                   job_data.get("working_dir") or None, job_data.get("artifacts") or None,
                   job_data.get("port_count") or None,
                   job_data.get("ports") or None, job_data.get("host_name") or None, requirements, previous_jobs,
                   master_job, apps, job_data.get("runner_id") or None, job_data.get("tag_name"))

    def create_job(self, job: Job, counter: List[int] = []):
        if len(counter) == 0:
            counter.append(0)
        client = self.__s3_client()
        job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
        job.set_id(job_id)
        lKey = self._l_key(job)
        client.put_object(Body="", Bucket=self.config.bucket_name, Key=lKey)
        prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
        key = f"{prefix}/{job_id}.yaml"
        client.put_object(Body=dump(self._serialize_job(job)), Bucket=self.config.bucket_name, Key=key)
        counter[0] += 1

    @staticmethod
    def _l_key(job: Job):
        prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
        lKey = f"{prefix}/l;{job.get_id()};" \
               f"{job.provider_name};{job.submitted_at};{job.status.value};" \
               f"{job.runner_id or ''};{','.join(job.artifacts or [])};" \
               f"{','.join(map(lambda a: a.app_name, job.apps or []))};{job.tag_name or ''}"
        return lKey

    # noinspection PyDefaultArgument
    def get_job(self, repo_user_name: str, repo_name: str, job_id: str) -> Job:
        client = self.__s3_client()
        prefix = f"jobs/{repo_user_name}/{repo_name}"
        key = f"{prefix}/{job_id}.yaml"
        obj = client.get_object(Bucket=self.config.bucket_name, Key=key)
        job = self._unserialize_job(yaml.load(obj['Body'].read().decode('utf-8'), yaml.FullLoader))
        job.set_id(job_id)
        return job

    def update_job(self, job: Job):
        client = self.__s3_client()
        prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
        lKeyPrefix = f"{prefix}/l;{job.get_id()};"
        response = client.list_objects_v2(Bucket=self.config.bucket_name, Prefix=lKeyPrefix, MaxKeys=1)
        for obj in response["Contents"]:
            client.delete_object(Bucket=self.config.bucket_name, Key=obj["Key"])
        lKey = self._l_key(job)
        client.put_object(Body="", Bucket=self.config.bucket_name, Key=lKey)
        key = f"{prefix}/{job.get_id()}.yaml"
        client.put_object(Body=dump(self._serialize_job(job)), Bucket=self.config.bucket_name, Key=key)

    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None):
        client = self.__s3_client()
        prefix = f"jobs/{repo_user_name}/{repo_name}"
        lKeyPrefix = f"{prefix}/l;"
        if run_name:
            lKeyPrefix += run_name
        response = client.list_objects_v2(Bucket=self.config.bucket_name, Prefix=lKeyPrefix, MaxKeys=1)
        job_heads = []
        for obj in response["Contents"]:
            job_id, provider_name, submitted_at, status, runner_id, artifacts, apps, tag_name = tuple(
                obj["Key"][len(lKeyPrefix):].split(';'))
            run_name, workflow_name, job_index = tuple(job_id.split(','))
            job_heads.append(JobHead(repo_user_name, repo_name,
                                     job_id, run_name, workflow_name or None, provider_name,
                                     JobStatus(status), int(submitted_at), runner_id or None,
                                     artifacts.split(',') or None, tag_name or None))
        return job_heads

    @staticmethod
    def _serialize_runner(runner: Runner) -> dict:
        resources = {
            "cpus": runner.resources.cpus,
            "memory_mib": runner.resources.memory_mib,
            "gpus": [{
                "name": gpu.name,
                "memory_mib": gpu.memory_mib,
            } for gpu in runner.resources.gpus],
            "interruptible": runner.resources.interruptible,
        }
        runner_data = {
            "runner_id": runner.runner_id,
            "request_id": runner.request_id,
            "resources": resources,
            "job": AwsBackend._serialize_job(job),
        }
        return runner_data

    def create_runner(self, runner: Runner):
        client = self.__s3_client()
        key = f"runners/{runner.runner_id}.yaml"
        client.put_object(Body=dump(self._serialize_runner(runner)), Bucket=self.config.bucket_name, Key=key)


def get_backend() -> Backend:
    config = load_config()
    if isinstance(config.backend, AwsBackendConfig):
        return AwsBackend(config.backend)
    else:
        raise Exception(f"Unsupported backend: {config.backend}")


if __name__ == '__main__':
    backend = get_backend()
    run_name = backend.next_run_name()
    job = Job(
        repo=Repo(repo_user_name="dstackai",
                  repo_name="dstack-examples",
                  repo_branch="main",
                  repo_hash="cc74bc6839db9232191f45f5e4704e763a1d47db", repo_diff=None),
        run_name=run_name,
        runner_id=None,
        submitted_at=int(round(time.time() * 1000)),
        provider_name="docker",
        image_name="ubuntu",
        status=JobStatus.SUBMITTED,
        workflow_name="train",
        variables=None,
        artifacts=["output"],
        requirements=Requirements(
            gpus=GpusRequirements(
                name="K80",
                count=1,
            )
        ),
        commands=[
            "mkdir -p output",
            "echo 'Hello, world!' > output/hello.txt",
        ],
        port_count=None
    )
    backend.create_job(job)
    print(job.get_id())
    runner_id = uuid.uuid4().hex

    # job = backend.get_job(repo_user_name="dstackai", repo_name="dstack-examples",
    #                     job_id="swift-eel-2,train,0")
    # job.runner_id = runner_id
    backend.update_job(job)

    print(job)

    runner = Runner(
        runner_id,
        request_id=uuid.uuid4().hex,
        resources=Resources(cpus=4, memory_mib=15258, gpus=[], interruptible=False),
        job=job
    )
    backend.create_runner(runner)
    # print(backend.get_job_heads(repo_user_name="dstackai", repo_name="dstack-examples"))
