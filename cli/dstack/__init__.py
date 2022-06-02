import json
import os
import sys
from abc import abstractmethod
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
                 gpu: Optional[Gpu] = None, shm_size: Optional[str] = None):
        self.cpu = cpu
        self.memory = memory
        self.gpu = gpu
        self.shm_size = shm_size


class JobRef:
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, id: Optional[str]):
        pass


class Job(JobRef):
    def __init__(self,
                 image: str,
                 commands: Optional[List[str]] = None,
                 environment: Dict[str, str] = None,
                 working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: int = 0,
                 ports: List[int] = None,
                 resources: Optional[Resources] = None,
                 depends_on: Optional[List[JobRef]] = None,
                 master: Optional[JobRef] = None):
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
        self.schema = schema
        # TODO: Move here workflow related fields, such as variables, etc
        self._validate_schema()
        pass

    @abstractmethod
    def create_jobs(self) -> List[Job]:
        pass

    def start(self):
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
                    del workflow_data["workflow_name"]
                    del workflow_data["repo_url"]
                    del workflow_data["repo_branch"]
                    del workflow_data["repo_hash"]
                    del workflow_data["repo_diff"]
                    del workflow_data["variables"]
                    del workflow_data["previous_job_ids"]
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
            if str(self.workflow.data["resources"].get("gpu")).isnumeric():
                gpu = int(self.workflow.data["resources"]["gpu"])
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
            if resources.cpu or resources.memory or resources.gpu or resources.shm_size:
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
        request_json = {
            "user_name": self.workflow.data["user_name"],
            "run_name": self.workflow.data["run_name"],
            "workflow_name": self.workflow.data["workflow_name"],
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
            "ports": {str(port) for port in job.ports} if job.ports else None,
            "environment": job.environment,
            "working_dir": job.working_dir,
            "master_job_id": job.master.get_id() if job.master else None
        }
        request_json_copy = dict(request_json)
        if self.workflow.data["repo_diff"]:
            request_json_copy["repo_diff"] = "<hidden, length is " + str(len(self.workflow.data["repo_diff"])) + ">"
        print("Request: " + str(request_json_copy))
        response = requests.request(method="POST", url=f"{os.environ['DSTACK_SERVER']}/jobs/submit",
                                    data=json.dumps(request_json).encode("utf-8"),
                                    headers=headers)
        if response.status_code != 200:
            response.raise_for_status()
        response_json = response.json()
        print("Response: " + str(response_json))
        if response.status_code == 200:
            job.id = response_json.get("job_id")
        else:
            response.raise_for_status()
