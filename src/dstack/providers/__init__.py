import os
import sys
import time
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional, List

import pkg_resources
import yaml
from jsonschema import validate, ValidationError

from dstack import Job, Requirements, GpusRequirements, JobSpec, Repo, JobStatus, JobRef
from dstack.backend import load_backend


class Workflow:
    def __init__(self, data: dict):
        self.data = data
        pass


def _str_to_mib(s: str) -> int:
    ns = s.replace(" ", "").lower()
    if ns.endswith('mib'):
        return int(s[:-3])
    elif ns.endswith('gib'):
        return int(s[:-3]) * 1024
    elif ns.endswith('mi'):
        return int(s[:-2])
    elif ns.endswith('gi'):
        return int(s[:-2]) * 1024
    elif ns.endswith('mb'):
        return int(int(s[:-2]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith('gb'):
        return int(int(s[:-2]) * (1000 * 1000 * 1000) / 1024 / 1024)
    elif ns.endswith('m'):
        return int(int(s[:-1]) * 1000 * 1000 / 1024 / 1024)
    elif ns.endswith('g'):
        return int(int(s[:-1]) * (1000 * 1000 * 1000) / 1024 / 1024)
    else:
        raise Exception(f"Unknown memory unit: {s}")


class Provider:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.workflow = None
        self.provider_args = None
        self.workflow_name = None
        self.run_as_provider = None
        self.schema = None
        self.loaded = False

    # TODO: This is a dirty hack
    def _save_python_version(self, name: str):
        v = self.workflow.data.get(name)
        if isinstance(v, str):
            return v
        elif v == 3.1:
            return "3.10"
        elif v:
            return str(v)
        else:
            return "3.10"

    # TODO: Rename to load, move _validate_schema to run
    def _load(self, schema: Optional[str] = None):
        self.workflow = Workflow(self._load_workflow_data())
        self.provider_args = [str(arg) for arg in self.workflow.data["provider_args"]] if self.workflow.data.get(
            "provider_args") else []
        self.workflow_name = self.workflow.data.get("workflow_name")
        self.run_as_provider = not self.workflow.data.get("workflow_name")
        self.parse_args()
        self.schema = pkg_resources.resource_string(self.__module__, '/'.join([schema])) if schema else None
        # TODO: Move here workflow related fields, such as variables, etc
        self._validate_schema()
        self.loaded = True

    @abstractmethod
    def load(self):
        pass

    # TODO: Add variables
    @abstractmethod
    def _create_parser(self, workflow_name: Optional[str]) -> Optional[ArgumentParser]:
        return None

    def help(self, workflow_name: Optional[str]):
        parser = self._create_parser(workflow_name)
        if parser:
            parser.print_help()

    @abstractmethod
    def create_job_specs(self) -> List[JobSpec]:
        pass

    @staticmethod
    def _add_base_args(parser: ArgumentParser):
        parser.add_argument("-r", "--requirements", type=str)
        parser.add_argument('-e', '--env', action='append')
        parser.add_argument('-a', '--artifact', action='append')
        # TODO: Support depends-on
        parser.add_argument("--working-dir", type=str)
        # parser.add_argument('--dep', action='append')
        parser.add_argument("-i", "--interruptible", action="store_true")
        parser.add_argument("--cpu", type=int)
        parser.add_argument("--memory", type=str)
        parser.add_argument("--gpu", type=int)
        parser.add_argument("--gpu-name", type=str)
        parser.add_argument("--gpu-memory", type=str)
        parser.add_argument("--shm-size", type=str)

    def _parse_base_args(self, args: Namespace):
        if args.requirements:
            self.workflow.data["requirements"] = args.requirements
        if args.artifact:
            self.workflow.data["artifacts"] = args.artifact
        if args.working_dir:
            self.workflow.data["working_dir"] = args.working_dir
        if args.env:
            environment = self.workflow.data.get("environment") or {}
            for e in args.env:
                if "=" in e:
                    tokens = e.split("=", maxsplit=1)
                    environment[tokens[0]] = tokens[1]
                else:
                    environment[e] = ""
            self.workflow.data["environment"] = environment
        if args.cpu or args.memory or args.gpu or args.gpu_name or args.gpu_memory or args.shm_size or args.interruptible:
            resources = self.workflow.data.get("resources") or {}
            self.workflow.data["resources"] = resources
            if args.cpu:
                resources["cpu"] = args.cpu
            if args.memory:
                resources["memory"] = args.memory
            if args.gpu or args.gpu_name or args.gpu_memory:
                gpu = self.workflow.data["resources"].get("gpu") or {} if self.workflow.data.get("resources") else {}
                if type(gpu) is int:
                    gpu = {
                        "count": gpu
                    }
                resources["gpu"] = gpu
                if args.gpu:
                    gpu["count"] = args.gpu
                if args.gpu_memory:
                    gpu["memory"] = args.gpu_memory
                if args.gpu_name:
                    gpu["name"] = args.gpu_name
            if args.shm_size:
                resources["shm_size"] = args.shm_size
            if args.interruptible:
                resources["interruptible"] = True

    def parse_args(self):
        pass

    def submit_jobs(self, run_name: Optional[str] = None) -> List[Job]:
        if not self.loaded:
            self.load()
        job_specs = self.create_job_specs()
        backend = load_backend()
        # [TODO] Handle previous jobs and master job
        jobs = []
        counter = []
        for job_spec in job_specs:
            previous_jobs = []
            if self.workflow.data.get("previous_job_ids"):
                for jid in self.workflow.data.get("previous_job_ids"):
                    previous_jobs.append(JobRef(str(jid)))
            if job_spec.previous_jobs:
                previous_jobs.extend(job_spec.previous_jobs)
            job = Job(
                Repo(repo_user_name=self.workflow.data["repo_user_name"], repo_name=self.workflow.data["repo_name"],
                     repo_branch=self.workflow.data["repo_branch"], repo_hash=self.workflow.data["repo_hash"],
                     repo_diff=self.workflow.data.get("repo_diff") or None, ),
                run_name or self.workflow.data["run_name"], self.workflow.data.get("workflow_name") or None,
                self.workflow.data.get("provider_name") or None, JobStatus.SUBMITTED, int(round(time.time() * 1000)),
                job_spec.image_name, job_spec.commands, self.workflow.data.get("variables") or None, job_spec.env,
                job_spec.working_dir, job_spec.artifacts, job_spec.port_count, None, None, job_spec.requirements,
                previous_jobs, job_spec.master_job, job_spec.apps, None, None)
            backend.submit_job(job, counter)
            jobs.append(job)
        job_ids = list(map(lambda j: j.id, jobs))
        self._serialize_job_ids(job_ids)
        return jobs

    @staticmethod
    def _serialize_job_ids(job_ids: List[str]):
        job_ids_file = Path(os.environ.get("JOB_IDS_CSV") or "job-ids.csv")
        if not job_ids_file.is_file():
            sys.exit("job-ids.csv is missing")
        with open(job_ids_file, 'w') as f:
            f.write(','.join(job_ids))

    def _validate_schema(self):
        if self.schema:
            try:
                workflow_data = dict(self.workflow.data)
                if "user_name" in workflow_data:
                    del workflow_data["user_name"]
                if "run_name" in workflow_data:
                    del workflow_data["run_name"]
                if "workflow_name" in workflow_data:
                    del workflow_data["workflow_name"]
                del workflow_data["repo_user_name"]
                del workflow_data["repo_name"]
                del workflow_data["repo_branch"]
                del workflow_data["repo_hash"]
                del workflow_data["repo_diff"]
                del workflow_data["variables"]
                del workflow_data["previous_job_ids"]
                if "provider_name" in workflow_data:
                    del workflow_data["provider_name"]
                if "provider_branch" in workflow_data:
                    del workflow_data["provider_branch"]
                if "provider_args" in workflow_data:
                    del workflow_data["provider_args"]
                if "depends-on" in workflow_data:
                    del workflow_data["depends_on"]
                if "working_dir" in workflow_data and workflow_data.get("working_dir") == '':
                    # This is a workaround to delete empty working_dir;
                    # TODO: This must be fixed in dstack-runner
                    #   Empty working_dir must not be included into workflow.yaml
                    del workflow_data["working_dir"]
                validate(workflow_data, yaml.load(self.schema, yaml.FullLoader))
            except ValidationError as e:
                workflow_file = Path(os.environ.get("WORKFLOW_YAML") or "workflow.yaml")
                sys.exit(f"There a syntax error in {workflow_file.resolve()}:\n\n{e}")

    def _resources(self) -> Optional[Requirements]:
        if self.workflow.data.get("resources"):
            resources = Requirements()
            if self.workflow.data["resources"].get("cpu"):
                if not str(self.workflow.data["resources"]["cpu"]).isnumeric():
                    sys.exit("resources.cpu in workflows.yaml should be an integer")
                cpu = int(self.workflow.data["resources"]["cpu"])
                if cpu > 0:
                    resources.cpus = cpu
            if self.workflow.data["resources"].get("memory"):
                resources.memory_mib = _str_to_mib(self.workflow.data["resources"]["memory"])
            gpu = self.workflow.data["resources"].get("gpu")
            if gpu:
                if str(gpu).isnumeric():
                    gpu = int(self.workflow.data["resources"]["gpu"])
                    if gpu > 0:
                        resources.gpus = GpusRequirements(gpu)
                else:
                    gpu_count = 0
                    gpu_name = None
                    if str(gpu.get("count")).isnumeric():
                        gpu_count = int(gpu.get("count"))
                    if gpu.get("name"):
                        gpu_name = gpu.get("name")
                        if not gpu_count:
                            gpu_count = 1
                    if gpu_count:
                        resources.gpus = GpusRequirements(gpu_count, name=gpu_name)
            for resource_name in self.workflow.data["resources"]:
                if resource_name.endswith("/gpu") and len(resource_name) > 4:
                    if not str(self.workflow.data["resources"][resource_name]).isnumeric():
                        sys.exit(f"resources.'{resource_name}' in workflows.yaml should be an integer")
                    gpu = int(self.workflow.data["resources"][resource_name])
                    if gpu > 0:
                        resources.gpus = GpusRequirements(gpu, name=resource_name[:-4])
            if self.workflow.data["resources"].get("shm_size"):
                resources.shm_size = self.workflow.data["resources"]["shm_size"]
            if self.workflow.data["resources"].get("interruptible"):
                resources.interruptible = self.workflow.data["resources"]["interruptible"]
            if resources.cpus or resources.memory_mib or resources.gpus or resources.shm_size or resources.interruptible:
                return resources
            else:
                return None

    @staticmethod
    def _load_workflow_data():
        # TODO: Check user_name, run_name, workflow_name, repo_user_name, repo_name, repo_branch, repo_hash
        if not os.environ.get("REPO_PATH"):
            sys.exit("REPO_PATH environment variable is not specified")
        if not os.path.isdir(os.environ["REPO_PATH"]):
            sys.exit("REPO_PATH environment variable doesn't point to a valid directory: " + os.environ["REPO_PATH"])
        # TODO: [instant_run] Use WORKFLOW_YAML_PATH environment  variable
        workflow_file = Path(os.environ.get("WORKFLOW_YAML") or "workflow.yaml")
        if not workflow_file.is_file():
            sys.exit("workflow.yaml is missing")
        with workflow_file.open() as f:
            return yaml.load(f, yaml.FullLoader)
