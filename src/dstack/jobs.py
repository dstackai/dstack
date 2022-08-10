from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any

from dstack.util import _quoted
from dstack.repo import Repo


class GpusRequirements:
    def __init__(self, count: Optional[int] = None, memory_mib: Optional[int] = None, name: Optional[str] = None):
        self.count = count
        self.memory_mib = memory_mib
        self.name = name

    def __str__(self) -> str:
        return f'GpusRequirements(count={self.count}, memory_mib={self.memory_mib}, ' \
               f'name={_quoted(self.name)})'


class Requirements:
    def __init__(self, cpus: Optional[int] = None, memory_mib: Optional[int] = None,
                 gpus: Optional[GpusRequirements] = None, shm_size: Optional[str] = None,
                 interruptible: Optional[bool] = None):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.shm_size = shm_size
        self.interruptible = interruptible

    def __str__(self) -> str:
        return f'Requirements(cpus={self.cpus}, memory_mib={self.memory_mib}, ' \
               f'gpus={self.gpus}, ' \
               f'shm_size={self.shm_size}, ' \
               f'interruptible={self.interruptible})'


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

    def __str__(self) -> str:
        return f'JobRefId(id="{self.id}")'


class JobApp:
    def __init__(self, port_index: int, app_name: str, url_path: Optional[str] = None,
                 url_query_params: Optional[Dict[str, str]] = None):
        self.port_index = port_index
        self.app_name = app_name
        self.url_path = url_path
        self.url_query_params = url_query_params

    def __str__(self) -> str:
        return f'App(app_name={self.app_name}, port_index={self.port_index}, ' \
               f'url_path={_quoted(self.url_path)}, url_query_params={self.url_query_params})'


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
        self.id = job_id
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
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

    def __str__(self) -> str:
        return f'JobHead(id="{self.id}", repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'runner_id={_quoted(self.runner_id)}, ' \
               f'artifacts={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifacts)) + "]") if self.artifacts else None}, ' \
               f'tag_name={_quoted(self.tag_name)})'


class Job(JobRef):
    def __init__(self, repo: Repo, run_name: str, workflow_name: Optional[str], provider_name: str,
                 status: JobStatus, submitted_at: int,
                 image_name: str, commands: Optional[List[str]] = None,
                 env: Dict[str, str] = None, working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: Optional[int] = None, ports: Optional[List[int]] = None,
                 host_name: Optional[str] = None,
                 requirements: Optional[Requirements] = None, previous_jobs: Optional[List[JobRef]] = None,
                 master_job: Optional[JobRef] = None, apps: Optional[List[JobApp]] = None,
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

    def __str__(self) -> str:
        return f'Job(id="{self.id}", repo={self.repo}, ' \
               f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'image_name="{self.image_name}", ' \
               f'commands={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]") if self.commands else None}, ' \
               f'env={self.env}, ' \
               f'working_dir={_quoted(self.working_dir)}, ' \
               f'port_count={self.port_count}, ' \
               f'ports={self.ports}, ' \
               f'host_name={_quoted(self.host_name)}, ' \
               f'artifacts={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifacts)) + "]") if self.artifacts else None}, ' \
               f'requirements={self.requirements}, ' \
               f'previous_jobs={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.previous_jobs)) + "]") if self.previous_jobs else None}, ' \
               f'master_job={self.master_job}, ' \
               f'apps={("[" + ", ".join(map(lambda a: str(a), self.apps)) + "]") if self.apps else None}, ' \
               f'runner_id={_quoted(self.runner_id)}, ' \
               f'tag_name={_quoted(self.tag_name)})'


class JobSpec(JobRef):
    def __init__(self, image_name: str, commands: Optional[List[str]] = None,
                 env: Dict[str, str] = None, working_dir: Optional[str] = None,
                 artifacts: Optional[List[str]] = None,
                 port_count: Optional[int] = None,
                 requirements: Optional[Requirements] = None, previous_jobs: Optional[List[JobRef]] = None,
                 master_job: Optional[JobRef] = None, apps: Optional[List[JobApp]] = None):
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

    def __str__(self) -> str:
        return f'JobSpec(id="{self.id}", image_name="{self.image_name}", ' \
               f'commands={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]") if self.commands else None}, ' \
               f'env={self.env}, ' \
               f'working_dir={_quoted(self.working_dir)}, ' \
               f'port_count={self.port_count}, ' \
               f'artifacts={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifacts)) + "]") if self.artifacts else None}, ' \
               f'requirements={self.requirements}, ' \
               f'previous_jobs={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.previous_jobs)) + "]") if self.previous_jobs else None}, ' \
               f'master_job={self.master_job}, ' \
               f'apps={("[" + ", ".join(map(lambda a: str(a), self.apps)) + "]") if self.apps else None})'
