from abc import ABC, abstractmethod
from functools import reduce, cmp_to_key
from typing import List, Optional

import boto3
import yaml
from botocore.client import BaseClient
from yaml import dump

from dstack import random_name, Job, Repo, JobStatus, JobRefId, App, Requirements, GpusRequirements, JobHead, \
    Runner, Resources, Gpu
from dstack.config import load_config, AwsBackendConfig


class InstanceType:
    def __init__(self, name: str, resources: Resources):
        self.name = name
        self.resources = resources

    def __str__(self) -> str:
        return f'InstanceType(name="{self.name}", resources={self.resources})'.__str__()


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
    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None) -> List[JobHead]:
        pass

    @abstractmethod
    def create_runner(self, runner_state: Runner):
        pass

    @abstractmethod
    def _get_instance_types(self) -> List[InstanceType]:
        pass

    def _pick_instance_type(self, requirements: Requirements) -> Optional[InstanceType]:
        instance_types = self._get_instance_types()

        def matches(resources: Resources):
            if requirements.cpus and requirements.cpus > resources.cpus:
                return False
            if requirements.memory_mib and requirements.memory_mib > resources.memory_mib:
                return False
            if requirements.gpus:
                gpu_count = requirements.gpus.count or 1
                if gpu_count > len(resources.gpus or []):
                    return False
                if requirements.gpus.name and gpu_count > len(
                        list(filter(lambda gpu: gpu.name == requirements.gpus.name,
                                    resources.gpus or []))):
                    return False
                if requirements.gpus.memory_mib and gpu_count > len(
                        list(filter(lambda gpu: gpu.memory_mib >= requirements.gpus.memory_mib,
                                    resources.gpus or []))):
                    return False
                if requirements.interruptible and not resources.interruptible:
                    return False
            return True

        return next(instance_type for instance_type in instance_types if matches(instance_type.resources))


class AwsAmi:
    def __init__(self, ami_id: str, ami_name: str):
        self.ami_id = ami_id
        self.ami_name = ami_name

    def __str__(self) -> str:
        return f'Ami(ami_id="{self.ami_id}", ami_name="{self.ami_name}")'


class AwsBackend(Backend):
    def __init__(self, config: AwsBackendConfig):
        self.config = config

    def __s3_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.config.profile_name, region_name=self.config.region_name)
        return session.client("s3")

    def __ec2_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.config.profile_name, region_name=self.config.region_name)
        return session.client("ec2")

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
                                     artifacts.split(',') if artifacts else None, tag_name or None))
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
            "job": AwsBackend._serialize_job(runner.job),
        }
        return runner_data

    def create_runner(self, runner: Runner):
        client = self.__s3_client()
        key = f"runners/{runner.runner_id}.yaml"
        client.put_object(Body=dump(self._serialize_runner(runner)), Bucket=self.config.bucket_name, Key=key)

    def _get_instance_types(self) -> List[InstanceType]:
        client = self.__ec2_client()
        response = None
        instance_types = []
        while not response or response.get("NextToken"):
            kwargs = {}
            if response and "NextToken" in response:
                kwargs["NextToken"] = response["NextToken"]
            response = client.describe_instance_types(
                Filters=[
                    {
                        'Name': 'instance-type',
                        'Values': ["c5.*", "m5.*", "p2.*", "p3.*", "p4.*", "p5.*"]
                    },
                ],
                **kwargs
            )
            for instance_type in response["InstanceTypes"]:
                gpus = [[Gpu(gpu['Name'], gpu['MemoryInfo']['SizeInMiB'])] * gpu['Count'] for gpu in
                        instance_type["GpuInfo"]["Gpus"]] if instance_type.get("GpuInfo") and instance_type[
                    "GpuInfo"].get("Gpus") else []
                instance_types.append(InstanceType(
                    instance_type["InstanceType"],
                    Resources(
                        instance_type["VCpuInfo"]["DefaultVCpus"],
                        instance_type["MemoryInfo"]["SizeInMiB"],
                        reduce(list.__add__, gpus) if gpus else [],
                        "spot" in instance_type["SupportedUsageClasses"],
                    )
                ))

        def compare(i1, i2):
            r1_gpu_total_memory_mib = sum(map(lambda g: g.memory_mib, i1.resources.gpus or []))
            r2_gpu_total_memory_mib = sum(map(lambda g: g.memory_mib, i2.resources.gpus or []))
            if r1_gpu_total_memory_mib < r2_gpu_total_memory_mib:
                return -1
            elif r1_gpu_total_memory_mib > r2_gpu_total_memory_mib:
                return 1
            if i1.resources.cpus < i2.resources.cpus:
                return -1
            elif i1.resources.cpus > i2.resources.cpus:
                return 1
            if i1.resources.memory_mib < i2.resources.memory_mib:
                return -1
            elif i1.resources.memory_mib > i2.resources.memory_mib:
                return 1
            return 0

        return sorted(instance_types, key=cmp_to_key(compare))

    def _get_ami_image_id(self, cuda: bool) -> Optional[AwsAmi]:
        client = self.__ec2_client()
        response = client.describe_images(Filters=[
            {
                'Name': 'name',
                'Values': [
                    'dstack-*'
                ]
            },
        ], )
        images = filter(lambda i: "cuda" in i["Name"], response["Images"])
        if images:
            ami = next(iter(sorted(images, key=lambda i: i["CreationDate"], reverse=True)))
            return AwsAmi(ami["ImageId"], ami["Name"])
        else:
            return None


def get_backend() -> Backend:
    config = load_config()
    if isinstance(config.backend, AwsBackendConfig):
        return AwsBackend(config.backend)
    else:
        raise Exception(f"Unsupported backend: {config.backend}")
