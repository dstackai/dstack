import base64
import json
import uuid
from abc import ABC, abstractmethod
from functools import reduce, cmp_to_key
from typing import List, Optional

import boto3
import yaml
from botocore.client import BaseClient
from yaml import dump

from dstack import random_name, Job, Repo, JobStatus, JobRefId, App, Requirements, GpusRequirements, JobHead, \
    Resources, Gpu, Runner, _quoted, version
from dstack.config import load_config, AwsBackendConfig


class InstanceType:
    def __init__(self, instance_name: str, resources: Resources):
        self.instance_name = instance_name
        self.resources = resources

    def __str__(self) -> str:
        return f'InstanceType(instance_name="{self.instance_name}", resources={self.resources})'.__str__()


class Run:
    def __init__(self, repo_user_name: str, repo_name: str, run_name: str, workflow_name: Optional[str],
                 provider_name: str, artifacts: Optional[List[str]], status: JobStatus, submitted_at: int,
                 tag_name: Optional[str]):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.artifacts = artifacts
        self.status = status
        self.submitted_at = submitted_at
        self.tag_name = tag_name
        self.apps = None
        self.availability_issues = None

    def __str__(self) -> str:
        return f'Run(repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'run_name="{self.run_name}", ' \
               f'workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'artifacts={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifacts)) + "]") if self.artifacts else None}, ' \
               f'tag_name={_quoted(self.tag_name)}, ' \
               f'apps={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.apps)) + "]") if self.apps else None}, ' \
               f'availability_issues={("[" + ", ".join(map(lambda i: _quoted(str(i)), self.availability_issues)) + "]") if self.availability_issues else None})'


class Backend(ABC):
    @abstractmethod
    def next_run_name(self):
        pass

    # noinspection PyDefaultArgument
    def submit_job(self, job: Job, counter: List[int] = []):
        pass

    # noinspection PyDefaultArgument
    @abstractmethod
    def _create_job(self, job: Job, counter: List[int] = []):
        pass

    @abstractmethod
    def _update_job(self, job: Job):
        pass

    @abstractmethod
    def get_job(self, repo_user_name: str, repo_name: str, job_id: str) -> Job:
        pass

    @abstractmethod
    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None) -> List[JobHead]:
        pass

    @abstractmethod
    def run_job(self, job: Job) -> Runner:
        pass

    @abstractmethod
    def _get_instance_types(self) -> List[InstanceType]:
        pass

    def _get_instance_type(self, requirements: Optional[Requirements]) -> Optional[InstanceType]:
        instance_types = self._get_instance_types()

        def matches(resources: Resources):
            if not requirements:
                return True
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

        instance_type = next(instance_type for instance_type in instance_types if matches(instance_type.resources))
        return InstanceType(instance_type.instance_name,
                            Resources(instance_type.resources.cpus, instance_type.resources.memory_mib,
                                      instance_type.resources.gpus, requirements and requirements.interruptible))

    @abstractmethod
    def _stop_runner(self, runner: Runner):
        pass

    @abstractmethod
    def stop_job(self, repo_user_name: str, repo_name: str, job_id: str, abort: bool):
        pass

    def stop_jobs(self, repo_user_name: str, repo_name: str, run_name: Optional[str],
                  workflow_name: Optional[str], abort: bool):
        job_heads = self.get_job_heads(repo_user_name, repo_name, run_name)
        if workflow_name:
            job_heads = filter(lambda j: j.workflow_name == workflow_name, job_heads)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(repo_user_name, repo_name, job_head.get_id(), abort)

    def get_runs(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None) -> List[Run]:
        runs_by_id = {}
        job_heads = self.get_job_heads(repo_user_name, repo_name, run_name)
        for job_head in job_heads:
            run_id = ','.join([job_head.run_name, job_head.workflow_name or ''])
            if run_id not in runs_by_id:
                run = Run(
                    repo_user_name,
                    repo_name,
                    job_head.run_name,
                    job_head.workflow_name,
                    job_head.provider_name,
                    job_head.artifacts or [],
                    job_head.status,
                    job_head.submitted_at,
                    job_head.tag_name,
                )
                runs_by_id[run_id] = run
            else:
                run = runs_by_id[run_id]
                run.submitted_at = min(run.submitted_at, job_head.submitted_at)
                if job_head.artifacts:
                    run.artifacts.extend(job_head.artifacts)
                if job_head.status.is_unfinished():
                    # TODO: implement max(status1, status2)
                    run.status = job_head.status

        runs = list(runs_by_id.values())
        return sorted(runs, key=lambda r: r.submitted_at, reverse=True)


class AwsAmi:
    def __init__(self, ami_id: str, ami_name: str):
        self.ami_id = ami_id
        self.ami_name = ami_name

    def __str__(self) -> str:
        return f'Ami(ami_id="{self.ami_id}", ami_name="{self.ami_name}")'


class AwsBackend(Backend):
    def __init__(self, backend_config: AwsBackendConfig):
        self.backend_config = backend_config

    def __s3_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("s3")

    def __ec2_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("ec2")

    def __iam_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("iam")

    def next_run_name(self):
        name = random_name.next_name()
        client = self.__s3_client()
        count = 0
        key = f"run-names/{name}.yaml"
        try:
            obj = client.get_object(Bucket=self.backend_config.bucket_name, Key=key)
            count = yaml.load(obj['Body'].read().decode('utf-8'), Loader=yaml.FullLoader)["count"]
            client.put_object(Body=dump({"count": count + 1}), Bucket=self.backend_config.bucket_name, Key=key)
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchKey":
                client.put_object(Body=dump({"count": count + 1}), Bucket=self.backend_config.bucket_name, Key=key)
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
        apps = ([App(a["port_index"], a["app_name"], a.get("url_path") or None, a.get("url_query_params") or None) for a
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

    # noinspection PyDefaultArgument
    def submit_job(self, job: Job, counter: List[int] = []):
        self._create_job(job)
        self.run_job(job)

    # noinspection PyDefaultArgument
    def _create_job(self, job: Job, counter: List[int] = []):
        if len(counter) == 0:
            counter.append(0)
        client = self.__s3_client()
        job_id = f"{job.run_name},{job.workflow_name or ''},{counter[0]}"
        job.set_id(job_id)
        lKey = self._l_key(job)
        client.put_object(Body="", Bucket=self.backend_config.bucket_name, Key=lKey)
        prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
        key = f"{prefix}/{job_id}.yaml"
        client.put_object(Body=dump(self._serialize_job(job)), Bucket=self.backend_config.bucket_name, Key=key)
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
        obj = client.get_object(Bucket=self.backend_config.bucket_name, Key=key)
        job = self._unserialize_job(yaml.load(obj['Body'].read().decode('utf-8'), yaml.FullLoader))
        job.set_id(job_id)
        return job

    def _update_job(self, job: Job):
        client = self.__s3_client()
        prefix = f"jobs/{job.repo.repo_user_name}/{job.repo.repo_name}"
        lKeyPrefix = f"{prefix}/l;{job.get_id()};"
        response = client.list_objects_v2(Bucket=self.backend_config.bucket_name, Prefix=lKeyPrefix, MaxKeys=1)
        for obj in response["Contents"]:
            client.delete_object(Bucket=self.backend_config.bucket_name, Key=obj["Key"])
        lKey = self._l_key(job)
        client.put_object(Body="", Bucket=self.backend_config.bucket_name, Key=lKey)
        key = f"{prefix}/{job.get_id()}.yaml"
        client.put_object(Body=dump(self._serialize_job(job)), Bucket=self.backend_config.bucket_name, Key=key)

    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None):
        client = self.__s3_client()
        prefix = f"jobs/{repo_user_name}/{repo_name}"
        lKeyPrefix = f"{prefix}/l;"
        lKeyRunPrefix = lKeyPrefix + run_name if run_name else lKeyPrefix
        response = client.list_objects_v2(Bucket=self.backend_config.bucket_name, Prefix=lKeyRunPrefix)
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

    @staticmethod
    def _serialize_runner(runner: Runner) -> dict:
        resources = {
            "cpus": runner.resources.cpus,
            "memory_mib": runner.resources.memory_mib,
            "gpus": [{
                "name": gpu.name,
                "memory_mib": gpu.memory_mib,
            } for gpu in runner.resources.gpus],
            "interruptible": runner.resources.interruptible is True,
        }
        data = {
            "runner_id": runner.runner_id,
            "request_id": runner.request_id,
            "resources": resources,
            "job": AwsBackend._serialize_job(runner.job),
        }
        return data

    @staticmethod
    def _unserialize_runner(data: dict) -> Runner:
        return Runner(
            data["runner_id"],
            data["request_id"],
            Resources(
                data["resources"]["cpus"],
                data["resources"]["memory_mib"],
                [Gpu(g["name"], g["memory_mib"]) for g in data["resources"]["gpus"]],
                data["resources"]["interruptible"] is True,
            ),
            AwsBackend._unserialize_job(data["job"]),
        )

    def _merge_runner(self, runner: Runner):
        client = self.__s3_client()
        key = f"runners/{runner.runner_id}.yaml"
        metadata = {}
        if runner.job.status == JobStatus.STOPPING:
            metadata["x-amz-meta-status"] = "stopping"
        client.put_object(Body=dump(self._serialize_runner(runner)), Bucket=self.backend_config.bucket_name,
                          Key=key, Metadata=metadata)

    def _create_runner(self, runner: Runner):
        self._merge_runner(runner)

    def _update_runner(self, runner: Runner):
        self._merge_runner(runner)

    def _get_security_group_id(self):
        client = self.__ec2_client()
        security_group_name = "dstack_security_group_" + self.backend_config.bucket_name.replace("-", "_").lower()
        security_group_id = None
        response = client.describe_security_groups(
            Filters=[
                {
                    'Name': 'group-name',
                    'Values': [
                        security_group_name,
                    ],
                },
            ],
        )
        if response.get("SecurityGroups"):
            security_group_id = response["SecurityGroups"][0]["GroupId"]
        else:
            security_group = client.create_security_group(
                Description="Generated by dstack",
                GroupName=security_group_name,
                TagSpecifications=[
                    {
                        "ResourceType": "security-group",
                        "Tags": [
                            {
                                "Key": "owner",
                                "Value": "dstack"
                            },
                            {
                                "Key": "dstack_bucket",
                                "Value": self.backend_config.bucket_name
                            },
                        ],
                    },
                ]
            )
            security_group_id = security_group["GroupId"]
            client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        "FromPort": 3000,
                        "ToPort": 4000,
                        "IpProtocol": "tcp",
                        "IpRanges": [
                            {
                                "CidrIp": "0.0.0.0/0"
                            }
                        ],
                    }
                ]
            )
            client.authorize_security_group_egress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "-1",
                    }
                ]
            )
        return security_group_id

    def serialize_config_yaml(self):
        return f"backend: aws\\n" \
               f"bucket: {self.backend_config.bucket_name}\\n" \
               f"region: {self.backend_config.region_name}\\n"

    @staticmethod
    def serialize_runner_yaml(runner_id: str,
                              resources: Resources,
                              runner_port_range_from: int,
                              runner_port_range_to: int):
        s = f"id: {runner_id}\\n" \
            f"expose_ports: {runner_port_range_from}-{runner_port_range_to}\\n" \
            f"resources:\\n"
        s += f"  cpus:{resources.cpus}\\n"
        if resources.gpus:
            s += "  gpus:\\n"
            for gpu in resources.gpus:
                s += f"    - name: {gpu.name}\\n      memory_mib: {gpu.memory_mib}\\n"
        if resources.interruptible:
            s += "  interruptible: true\\n"
        return s

    def _user_data(self, runner_id: str, resources: Resources,
                   port_range_from: int = 3000, port_range_to: int = 4000) -> str:
        sysctl_port_range_from = int((port_range_to - port_range_from) / 2) + port_range_from
        sysctl_port_range_to = port_range_to - 1
        runner_port_range_from = port_range_from
        runner_port_range_to = sysctl_port_range_from - 1
        user_data = f"""#!/bin/bash
if [ -e "/etc/fuse.conf" ]
then
   sudo sed "s/# *user_allow_other/user_allow_other/" /etc/fuse.conf > t
   sudo mv t /etc/fuse.conf
else
   echo "user_allow_other" | sudo tee -a /etc/fuse.conf > /dev/null
fi
sudo sysctl -w net.ipv4.ip_local_port_range="{sysctl_port_range_from} ${sysctl_port_range_to}"
mkdir -p /root/.dstack/
echo $'{self.serialize_config_yaml()}' > /root/.dstack/config.yaml
echo $'{AwsBackend.serialize_runner_yaml(runner_id, resources, runner_port_range_from, runner_port_range_to)}' > /root/.dstack/runner.yaml
die() {{ status=$1; shift; echo "FATAL: $*"; exit $status; }}
EC2_PUBLIC_HOSTNAME="`wget -q -O - http://169.254.169.254/latest/meta-data/public-hostname || die \"wget public-hostname has failed: $?\"`"
echo "hostname: $EC2_PUBLIC_HOSTNAME" >> /root/.dstack/runner.yaml
HOME=/root nohup dstack-runner start &
"""
        return user_data

    def _role_arn(self) -> str:
        client = self.__iam_client()
        policy_name = "dstack_policy_" + self.backend_config.bucket_name.replace("-", "_").lower()
        role_name = "dstack_role_" + self.backend_config.bucket_name.replace("-", "_").lower()
        role_id = None
        try:
            response = client.get_role(RoleName=role_name)
            role_id = response["Role"]["RoleId"]
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchEntity":
                response = client.create_policy(
                    PolicyName=policy_name,
                    Description="Generated by dstack",
                    PolicyDocument=json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": "s3:*",
                                    "Resource": [f"arn:aws:s3:::{self.backend_config.bucket_name}",
                                                 f"arn:aws:s3:::{self.backend_config.bucket_name}/*"]
                                },
                                {
                                    "Effect": "Allow",
                                    "Action": "logs:*",
                                    "Resource": [
                                        f"arn:aws:logs:::log-group:/dstack/jobs/{self.backend_config.bucket_name}*",
                                        f"arn:aws:logs:::log-group:/dstack/runners/{self.backend_config.bucket_name}*"]
                                },
                                {
                                    "Effect": "Allow",
                                    "Action": "ec2:*",
                                    "Resource": ["*"],
                                    "Condition": {
                                        "StringEquals": {
                                            "aws:ResourceTag/dstack_bucket": self.backend_config.bucket_name,
                                        }
                                    }
                                },
                            ]
                        }),
                    Tags=[
                        {
                            "Key": "owner",
                            "Value": "dstack"
                        },
                        {
                            "Key": "dstack_bucket",
                            "Value": self.backend_config.bucket_name
                        },
                    ]
                )
                policy_arn = response['Policy']['Arn']
                response = client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Action": "sts:AssumeRole",
                                    "Effect": "Allow",
                                    "Principal": {
                                        "Service": "ec2.amazonaws.com"
                                    }
                                }
                            ]
                        }),
                    Description="Generated by dstack",
                    MaxSessionDuration=3600,
                    PermissionsBoundary=policy_arn,
                    Tags=[
                        {
                            "Key": "owner",
                            "Value": "dstack"
                        },
                        {
                            "Key": "dstack_bucket",
                            "Value": self.backend_config.bucket_name
                        },
                    ],
                )
                role_id = response["Role"]["RoleId"]
                client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn
                )
            else:
                raise e
        return role_id

    def _instance_profile_arn(self):
        client = self.__iam_client()
        role_name = "dstack_role_" + self.backend_config.bucket_name.replace("-", "_").lower()
        instance_profile_arn = None
        try:
            response = client.get_instance_profile(InstanceProfileName=role_name)
            return response["InstanceProfile"]["Arn"]
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchEntity":
                self._role_arn()
                response = client.create_instance_profile(
                    InstanceProfileName=role_name,
                    Tags=[
                        {
                            "Key": "owner",
                            "Value": "dstack"
                        },
                        {
                            "Key": "dstack_bucket",
                            "Value": self.backend_config.bucket_name
                        },
                    ],
                )
                instance_profile_arn = response["InstanceProfile"]["Arn"]
                client.add_role_to_instance_profile(
                    InstanceProfileName=role_name,
                    RoleName=role_name,
                )
                return instance_profile_arn
            else:
                raise e

    def _create_spot_request(self, runner_id: str, instance_type: InstanceType) -> str:
        client = self.__ec2_client()
        response = client.request_terminate_instances(
            InstanceCount=1,
            Type="persistent",
            LaunchSpecification={
                "ImageId": self._get_ami_image(len(instance_type.resources.gpus) > 0).ami_id,
                "InstanceType": instance_type.instance_name,
                "SecurityGroupIds": [self._get_security_group_id()],
                "BlockDeviceMappings": [
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 100,
                            "VolumeType": "gp2",
                        },
                    }
                ],
                "IamInstanceProfile": {
                    "Arn": self._instance_profile_arn(),
                },
                "UserData": base64.b64encode(
                    self._user_data(runner_id, instance_type.resources).encode("ascii")).decode('ascii')
            },
            TagSpecifications=[
                {
                    "ResourceType": "spot-instances-request",
                    "Tags": [
                        {
                            "Key": "owner",
                            "Value": "dstack"
                        },
                        {
                            "Key": "dstack_bucket",
                            "Value": self.backend_config.bucket_name
                        },
                    ],
                },
            ]
        )
        request_id = response["SpotInstanceRequests"][0]["SpotInstanceRequestId"]
        return request_id

    def _run_instance(self, runner_id: str, instance_type: InstanceType) -> str:
        client = self.__ec2_client()
        response = client.run_instances(
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": 100,
                        "VolumeType": "gp2",
                    },
                }
            ],
            ImageId=self._get_ami_image(len(instance_type.resources.gpus) > 0).ami_id,
            InstanceType=instance_type.instance_name,
            MinCount=1,
            MaxCount=1,
            SecurityGroupIds=[self._get_security_group_id()],
            IamInstanceProfile={
                "Arn": self._instance_profile_arn(),
            },
            UserData=self._user_data(runner_id, instance_type.resources),
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {
                            "Key": "owner",
                            "Value": "dstack"
                        },
                        {
                            "Key": "dstack_bucket",
                            "Value": self.backend_config.bucket_name
                        },
                    ],
                },
            ]
        )
        instance_id = response["Instances"][0]["InstanceId"]
        return instance_id

    def run_job(self, job: Job) -> Runner:
        if job.status == JobStatus.SUBMITTED:
            instance_type = self._get_instance_type(job.requirements)
            runner_id = uuid.uuid4().hex
            job.runner_id = runner_id
            self._update_job(job)
            runner = Runner(runner_id, None, instance_type.resources, job)
            self._create_runner(runner)
            if instance_type.resources.interruptible:
                request_id = self._create_spot_request(runner_id, instance_type)
            else:
                request_id = self._run_instance(runner_id, instance_type)
            runner.request_id = request_id
            self._update_runner(runner)
            return runner
        else:
            raise Exception("Can't create a request for a job which status is not SUBMITTED")

    def _delete_runner(self, runner: Runner):
        client = self.__s3_client()
        key = f"runners/{runner.runner_id}.yaml"
        client.delete_object(Bucket=self.backend_config.bucket_name, Key=key)

    def _get_runner(self, runner_id: str) -> Optional[Runner]:
        client = self.__s3_client()
        key = f"runners/{runner_id}.yaml"
        try:
            obj = client.get_object(Bucket=self.backend_config.bucket_name, Key=key)
            return self._unserialize_runner(yaml.load(obj['Body'].read().decode('utf-8'), yaml.FullLoader))
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error") and e.response["Error"].get("Code") == "NoSuchKey":
                return None
            else:
                raise e

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

    def _get_ami_image(self, cuda: bool) -> AwsAmi:
        client = self.__ec2_client()
        response = client.describe_images(Filters=[
            {
                'Name': 'name',
                'Values': [
                    'dstack-*' if version.__is_release__ else '[stgn] dstack-*'
                ]
            },
        ], )
        images = filter(lambda i: cuda == ("cuda" in i["Name"]), response["Images"])
        if images:
            ami = next(iter(sorted(images, key=lambda i: i["CreationDate"], reverse=True)))
            return AwsAmi(ami["ImageId"], ami["Name"])
        else:
            raise Exception(f"Can't find an AMI image 'dstack-*' (cuda={cuda})")

    def _cancel_spot_request(self, request_id: str):
        client = self.__ec2_client()
        client.cancel_terminate_instance_requests(SpotInstanceRequestIds=[request_id])
        response = client.describe_instances(
            Filters=[
                {
                    'Name': 'spot-instance-request-id',
                    'Values': ['request_id']
                },
            ],
        )
        if response.get("Reservations"):
            client.terminate_instances(InstanceIds=[response["Reservations"][0]["InstanceId"]])

    def _terminate_instance(self, request_id: str):
        client = self.__ec2_client()
        client.terminate_instances(InstanceIds=[request_id])

    def _stop_runner(self, runner: Runner):
        if runner.resources.interruptible:
            self._cancel_spot_request(runner.request_id)
        else:
            self._terminate_instance(runner.request_id)
        self._delete_runner(runner)

    def stop_job(self, repo_user_name: str, repo_name: str, job_id: str, abort: bool):
        job = self.get_job(repo_user_name, repo_name, job_id)
        if job.status.is_unfinished():
            if abort:
                new_status = JobStatus.ABORTED
            elif job.status == JobStatus.SUBMITTED:
                new_status = JobStatus.STOPPED
            else:
                new_status = JobStatus.STOPPING
            runner = self._get_runner(job.runner_id)
            if runner:
                if new_status.is_finished():
                    self._stop_runner(runner)
                else:
                    runner.job.status = new_status
                    self._update_runner(runner)
            job.status = new_status
            self._update_job(job)


def load_backend() -> Backend:
    config = load_config()
    if isinstance(config.backend_config, AwsBackendConfig):
        return AwsBackend(config.backend_config)
    else:
        raise Exception(f"Unsupported backend: {config.backend_config}")
