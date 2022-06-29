import json
import os
import sys
from abc import abstractmethod
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional, List, Dict

import requests
import yaml
from jsonschema import validate, ValidationError


class Gpu:
    def __init__(self, count: Optional[int] = None, memory: Optional[str] = None, name: Optional[str] = None):
        self.count = count
        self.memory = memory
        self.name = name


class Resources:
    def __init__(self, cpu: Optional[int] = None, memory: Optional[str] = None,
                 gpu: Optional[Gpu] = None, shm_size: Optional[str] = None,
                 interruptible: Optional[bool] = None):
        self.cpu = cpu
        self.memory = memory
        self.gpu = gpu
        self.shm_size = shm_size
        self.interruptible = interruptible


class JobRef:
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, id: Optional[str]):
        pass


class App:
    def __init__(self,
                 port_index: int,
                 app_name: str,
                 url_path: Optional[str] = None,
                 url_query_params: Optional[Dict[str, str]] = None):
        self.port_index = port_index
        self.app_name = app_name
        self.url_path = url_path
        self.url_query_params = url_query_params


class Job(JobRef):
    def __init__(self,
                 image: str,
                 commands: Optional[List[str]] = None,
                 environment: Dict[str, str] = None,
                 working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: Optional[int] = None,
                 ports: Optional[List[int]] = None,
                 resources: Optional[Resources] = None,
                 depends_on: Optional[List[JobRef]] = None,
                 master: Optional[JobRef] = None,
                 apps: Optional[List[App]] = None):
        self.id = None
        self.image = image
        self.commands = commands
        self.environment = environment
        self.working_dir = working_dir
        self.port_count = port_count
        self.ports = ports
        self.artifacts = artifacts
        self.resources = resources
        self.depends_on = depends_on
        self.master = master
        self.apps = apps

    def get_id(self) -> Optional[str]:
        return self.id

    def set_id(self, id: Optional[str]):
        self.id = id


class Workflow:
    def __init__(self, data: dict):
        self.data = data
        pass


class Provider:
    def __init__(self, schema: Optional[str] = None):
        self.workflow = Workflow(self._load_workflow_data())
        self.provider_args = [str(arg) for arg in self.workflow.data["provider_args"]] if self.workflow.data.get(
            "provider_args") else []
        self.workflow_name = self.workflow.data.get("workflow_name")
        self.run_as_provider = not self.workflow.data.get("workflow_name")
        self.parse_args()
        self.schema = schema
        # TODO: Move here workflow related fields, such as variables, etc
        self._validate_schema()

    @abstractmethod
    def create_jobs(self) -> List[Job]:
        pass

    @staticmethod
    def _add_base_args(parser: ArgumentParser):
        parser.add_argument("-r", "--requirements", type=str, nargs="?")
        parser.add_argument('-e', '--env', action='append', nargs="?")
        parser.add_argument('-a', '--artifact', action='append', nargs="?")
        # TODO: Support depends-on
        parser.add_argument("--working-dir", type=str, nargs="?")
        # parser.add_argument('--depends-on', action='append', nargs="?")
        parser.add_argument("-i", "--interruptible", action="store_true")
        parser.add_argument("--cpu", type=int, nargs="?")
        parser.add_argument("--memory", type=str, nargs="?")
        parser.add_argument("--gpu", type=int, nargs="?")
        parser.add_argument("--gpu-name", type=str, nargs="?")
        parser.add_argument("--gpu-memory", type=str, nargs="?")
        parser.add_argument("--shm-size", type=str, nargs="?")

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

    def start(self):
        # print("Workflow data: " + str(self.workflow.data))
        jobs = self.create_jobs()
        # TODO: Handle previous jobs and master job
        for job in jobs:
            self._submit(job)
        job_ids = list(map(lambda j: j.id, jobs))
        self._serialize_job_ids(job_ids)
        pass

    @staticmethod
    def _serialize_job_ids(job_ids: List[str]):
        job_ids_file = Path("job-ids.csv")
        if not job_ids_file.is_file():
            sys.exit("job-ids.csv is missing")
        with open(job_ids_file, 'w') as f:
            f.write(','.join(job_ids))

    def _validate_schema(self):
        if self.schema:
            schema_file = Path(self.schema)
            if not schema_file.is_file():
                sys.exit(f"{self.schema} is missing")
            with schema_file.open() as f:
                try:
                    workflow_data = dict(self.workflow.data)
                    del workflow_data["user_name"]
                    del workflow_data["run_name"]
                    if "workflow_name" in workflow_data:
                        del workflow_data["workflow_name"]
                    del workflow_data["repo_url"]
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
                    validate(workflow_data, yaml.load(f, yaml.FullLoader))
                except ValidationError as e:
                    sys.exit(f"There a syntax error in {os.getcwd()}/.dstack/workflows.yaml:\n\n{e}")

    def _resources(self) -> Optional[Resources]:
        if self.workflow.data.get("resources"):
            resources = Resources()
            if self.workflow.data["resources"].get("cpu"):
                if not str(self.workflow.data["resources"]["cpu"]).isnumeric():
                    sys.exit("resources.cpu in workflows.yaml should be an integer")
                cpu = int(self.workflow.data["resources"]["cpu"])
                if cpu > 0:
                    resources.cpu = cpu
            if self.workflow.data["resources"].get("memory"):
                resources.memory = self.workflow.data["resources"]["memory"]
            gpu = self.workflow.data["resources"].get("gpu")
            if gpu:
                if str(gpu).isnumeric():
                    gpu = int(self.workflow.data["resources"]["gpu"])
                    if gpu > 0:
                        resources.gpu = Gpu(gpu)
                elif str(gpu.get("count")).isnumeric():
                    gpu = int(gpu.get("count"))
                    if gpu > 0:
                        resources.gpu = Gpu(gpu)
            for resource_name in self.workflow.data["resources"]:
                if resource_name.endswith("/gpu") and len(resource_name) > 4:
                    if not str(self.workflow.data["resources"][resource_name]).isnumeric():
                        sys.exit(f"resources.'{resource_name}' in workflows.yaml should be an integer")
                    gpu = int(self.workflow.data["resources"][resource_name])
                    if gpu > 0:
                        resources.gpu = Gpu(gpu, name=resource_name[:-4])
            if self.workflow.data["resources"].get("shm_size"):
                resources.shm_size = self.workflow.data["resources"]["shm_size"]
            if self.workflow.data["resources"].get("interruptible"):
                resources.interruptible = self.workflow.data["resources"]["interruptible"]
            if resources.cpu or resources.memory or resources.gpu or resources.shm_size or resources.interruptible:
                return resources
            else:
                return None

    @staticmethod
    def _load_workflow_data():
        # TODO: Check user_name, run_name, workflow_name, repo_url, repo_branch, repo_hash
        if not os.environ.get("DSTACK_SERVER"):
            sys.exit("DSTACK_SERVER environment variable is not specified")
        if not os.environ.get("DSTACK_TOKEN"):
            sys.exit("DSTACK_TOKEN environment variable is not specified")
        if not os.environ.get("REPO_PATH"):
            sys.exit("REPO_PATH environment variable is not specified")
        if not os.path.isdir(os.environ["REPO_PATH"]):
            sys.exit("REPO_PATH environment variable doesn't point to a valid directory: " + os.environ["REPO_PATH"])
        workflow_file = Path("workflow.yaml")
        if not workflow_file.is_file():
            sys.exit("workflow.yaml is missing")
        with workflow_file.open() as f:
            return yaml.load(f, yaml.FullLoader)

    def _submit(self, job: Job):
        token = os.environ["DSTACK_TOKEN"]
        headers = {
            "Content-Type": f"application/json; charset=utf-8",
            "Authorization": f"Bearer {token}"
        }
        previous_job_ids = []
        if self.workflow.data.get("previous_job_ids"):
            for jid in self.workflow.data.get("previous_job_ids"):
                previous_job_ids.append(str(jid))
        if job.depends_on:
            for j in job.depends_on:
                previous_job_ids.append(j.get_id())
        resources = None
        if job.resources:
            resources = {}
            if job.resources.cpu:
                resources["cpu"] = {
                    "count": job.resources.cpu
                }
            if job.resources.memory:
                resources["memory"] = job.resources.memory
            if job.resources.gpu:
                resources["gpu"] = {
                    "count": job.resources.gpu.count
                }
                if job.resources.gpu.memory:
                    resources["gpu"]["memory"] = job.resources.gpu.memory
                if job.resources.gpu.name:
                    resources["gpu"]["name"] = job.resources.gpu.name
            if job.resources.shm_size:
                resources["shm_size"] = job.resources.shm_size
            if job.resources.interruptible:
                resources["interruptible"] = job.resources.interruptible
        request_json = {
            "user_name": self.workflow.data["user_name"],
            "run_name": self.workflow.data["run_name"],
            "workflow_name": self.workflow.data.get("workflow_name") or None,
            "previous_job_ids": previous_job_ids or None,
            "repo_url": self.workflow.data["repo_url"],
            "repo_branch": self.workflow.data["repo_branch"],
            "repo_hash": self.workflow.data["repo_hash"],
            "repo_diff": self.workflow.data.get("repo_diff") or None,
            "variables": self.workflow.data.get("variables") or None,
            "artifacts": job.artifacts,
            "resources": resources,
            "image_name": job.image,
            "commands": job.commands,
            "port_count": job.port_count if job.port_count else None,
            "ports": [str(port) for port in job.ports] if job.ports else None,
            "environment": job.environment,
            "working_dir": job.working_dir,
            "master_job_id": job.master.get_id() if job.master else None,
            "apps": [{
                "port_index": app.port_index,
                "app_name": app.app_name,
                "url_path": app.url_path if app.url_path else None,
                "url_query_params": app.url_query_params if app.url_query_params else None,
            } for app in job.apps] if job.apps else None
        }
        request_json_copy = dict(request_json)
        if self.workflow.data["repo_diff"]:
            request_json_copy["repo_diff"] = "<hidden, length is " + str(len(self.workflow.data["repo_diff"])) + ">"
        # print("Request: " + str(request_json_copy))
        response = requests.request(method="POST", url=f"{os.environ['DSTACK_SERVER']}/jobs/submit",
                                    data=json.dumps(request_json).encode("utf-8"),
                                    headers=headers)
        if response.status_code != 200:
            response.raise_for_status()
        response_json = response.json()
        # print("Response: " + str(response_json))
        if response.status_code == 200:
            job.id = response_json.get("job_id")
        else:
            response.raise_for_status()
