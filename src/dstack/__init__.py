from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any


class GpusRequirements:
    def __init__(self, count: Optional[int] = None, memory_mib: Optional[int] = None, name: Optional[str] = None):
        self.count = count
        self.memory_mib = memory_mib
        self.name = name


class Requirements:
    def __init__(self, cpus: Optional[int] = None, memory_mib: Optional[int] = None,
                 gpus: Optional[GpusRequirements] = None, shm_size: Optional[str] = None,
                 interruptible: Optional[bool] = None):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.shm_size = shm_size
        self.interruptible = interruptible


class JobRef:
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, id: Optional[str]):
        pass


class JobRefId(JobRef):
    def get_id(self) -> Optional[str]:
        return self.id

    def set_id(self, id: Optional[str]):
        self.id = id

    def __init__(self, id: str):
        self.id = id


class App:
    def __init__(self, port_index: int, app_name: str, url_path: Optional[str] = None,
                 url_query_params: Optional[Dict[str, str]] = None):
        self.port_index = port_index
        self.app_name = app_name
        self.url_path = url_path
        self.url_query_params = url_query_params


class Repo:
    def __init__(self, repo_user_name: str, repo_name: str, repo_branch: str, repo_hash: str, repo_diff: Optional[str]):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.repo_branch = repo_branch
        self.repo_hash = repo_hash
        self.repo_diff = repo_diff


class JobStatus(Enum):
    SUBMITTED = "submitted"
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"
    DONE = "done"

    def is_finished(self):
        return self in [self.STOPPED, self.ABORTED, self.FAILED, self.DONE]

    def is_unfinished(self):
        return not self.is_finished()


class JobHead(JobRef):
    def __init__(self, repo_user_name: str, repo_name: str, job_id: str, run_name: str, workflow_name: Optional[str],
                 provider_name: str, status: JobStatus, submitted_at: int, runner_id: Optional[str],
                 artifacts: Optional[List[str]], tag_name: Optional[str]):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.id = job_id
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.status = status
        self.submitted_at = submitted_at
        self.runner_id = runner_id
        self.artifacts = artifacts
        self.tag_name = tag_name

    def get_id(self) -> Optional[str]:
        return self.id

    def set_id(self, id: Optional[str]):
        self.id = id


class Job(JobRef):
    def __init__(self, repo: Repo, run_name: str, workflow_name: Optional[str], provider_name: str,
                 status: JobStatus, submitted_at: int,
                 image_name: str, commands: Optional[List[str]] = None, variables: Dict[str, Any] = None,
                 env: Dict[str, str] = None, working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: Optional[int] = None, ports: Optional[List[int]] = None,
                 host_name: Optional[str] = None,
                 requirements: Optional[Requirements] = None, previous_jobs: Optional[List[JobRef]] = None,
                 master_job: Optional[JobRef] = None, apps: Optional[List[App]] = None,
                 runner_id: Optional[str] = None,
                 tag_name: Optional[str] = None):
        self.id = None
        self.repo = repo
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.status = status
        self.submitted_at = submitted_at
        self.image_name = image_name
        self.commands = commands
        self.variables = variables
        self.env = env
        self.working_dir = working_dir
        self.port_count = port_count
        self.ports = ports
        self.host_name = host_name
        self.artifacts = artifacts
        self.requirements = requirements
        self.previous_jobs = previous_jobs
        self.master_job = master_job
        self.apps = apps
        self.runner_id = runner_id
        self.tag_name = tag_name

    def get_id(self) -> Optional[str]:
        return self.id

    def set_id(self, id: Optional[str]):
        self.id = id


class JobSpec(JobRef):
    def __init__(self, image_name: str, commands: Optional[List[str]] = None,
                 env: Dict[str, str] = None, working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: Optional[int] = None,
                 requirements: Optional[Requirements] = None, previous_jobs: Optional[List[JobRef]] = None,
                 master_job: Optional[JobRef] = None, apps: Optional[List[App]] = None):
        self.id = None
        self.image_name = image_name
        self.commands = commands
        self.env = env
        self.working_dir = working_dir
        self.port_count = port_count
        self.artifacts = artifacts
        self.requirements = requirements
        self.previous_jobs = previous_jobs
        self.master_job = master_job
        self.apps = apps

    def get_id(self) -> Optional[str]:
        return self.id

    def set_id(self, id: Optional[str]):
        self.id = id


class Gpu:
    def __init__(self, name: str, memory_mib: int):
        self.memory_mib = memory_mib
        self.name = name


class Resources:
    def __init__(self, cpus: int, memory_mib: int, gpus: Optional[List[Gpu]], interruptible: bool):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.interruptible = interruptible


class Runner:
    def __init__(self, runner_id: str, request_id: str, resources: Resources, job: Job):
        self.runner_id = runner_id
        self.request_id = request_id
        self.job = job
        self.resources = resources
