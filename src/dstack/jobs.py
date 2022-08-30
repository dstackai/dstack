from abc import abstractmethod
from enum import Enum
from typing import Optional, List, Dict

from dstack.repo import RepoData
from dstack.util import _quoted


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
                 gpus: Optional[GpusRequirements] = None, shm_size_mib: Optional[int] = None,
                 interruptible: Optional[bool] = None):
        self.cpus = cpus
        self.memory_mib = memory_mib
        self.gpus = gpus
        self.shm_size_mib = shm_size_mib
        self.interruptible = interruptible

    def __str__(self) -> str:
        return f'Requirements(cpus={self.cpus}, memory_mib={self.memory_mib}, ' \
               f'gpus={self.gpus}, ' \
               f'shm_size_mib={self.shm_size_mib}, ' \
               f'interruptible={self.interruptible})'


class JobRef:
    @abstractmethod
    def get_id(self) -> Optional[str]:
        pass

    @abstractmethod
    def set_id(self, job_id: Optional[str]):
        pass


class JobRefId(JobRef):
    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __init__(self, job_id: str):
        self.job_id = job_id

    def __str__(self) -> str:
        return f'JobRefId(job_id="{self.job_id}")'


class AppSpec:
    def __init__(self, port_index: int, app_name: str, url_path: Optional[str] = None,
                 url_query_params: Optional[Dict[str, str]] = None):
        self.port_index = port_index
        self.app_name = app_name
        self.url_path = url_path
        self.url_query_params = url_query_params

    def __str__(self) -> str:
        return f'AppSpec(app_name={self.app_name}, port_index={self.port_index}, ' \
               f'url_path={_quoted(self.url_path)}, url_query_params={self.url_query_params})'


class JobStatus(Enum):
    SUBMITTED = "submitted"
    DOWNLOADING = "downloading"
    RUNNING = "running"
    UPLOADING = "uploading"
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
    def __init__(self, job_id: str, repo_user_name: str, repo_name: str, run_name: str, workflow_name: Optional[str],
                 provider_name: str, status: JobStatus, submitted_at: int, artifact_paths: Optional[List[str]],
                 tag_name: Optional[str],
                 app_names: Optional[List[str]]):
        self.job_id = job_id
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.status = status
        self.submitted_at = submitted_at
        self.artifact_paths = artifact_paths
        self.tag_name = tag_name
        self.app_names = app_names

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        artifact_paths = ("[" + ", ".join(
            map(lambda a: _quoted(str(a)), self.artifact_paths)) + "]") if self.artifact_paths else None
        app_names = ("[" + ", ".join(map(lambda a: _quoted(a), self.app_names)) + "]") if self.app_names else None
        return f'JobHead(job_id="{self.job_id}", repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'artifact_paths={artifact_paths}, ' \
               f'tag_name={_quoted(self.tag_name)}, ' \
               f'app_names={app_names})'


class DepSpec:
    def __init__(self, repo_user_name: str, repo_name: str, run_name: str, mount: bool):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.run_name = run_name
        self.mount = mount

    def __str__(self) -> str:
        return f'DepSpec(repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'run_name="{self.run_name}",' \
               f'mount={self.mount})'


class ArtifactSpec:
    def __init__(self, artifact_path: str, mount: bool):
        self.artifact_path = artifact_path
        self.mount = mount

    def __str__(self) -> str:
        return f'ArtifactSpec(artifact_path="{self.artifact_path}", ' \
               f'mount={self.mount})'


class Job(JobHead):
    def __init__(self, job_id: Optional[str], repo_data: RepoData, run_name: str, workflow_name: Optional[str],
                 provider_name: str, status: JobStatus, submitted_at: int, image_name: str,
                 commands: Optional[List[str]], env: Optional[Dict[str, str]], working_dir: Optional[str],
                 artifact_specs: Optional[List[ArtifactSpec]], port_count: Optional[int], ports: Optional[List[int]],
                 host_name: Optional[str], requirements: Optional[Requirements], dep_specs: Optional[List[DepSpec]],
                 master_job: Optional[JobRef], app_specs: Optional[List[AppSpec]], runner_id: Optional[str],
                 request_id: Optional[str], tag_name: Optional[str]):
        super().__init__(job_id, repo_data.repo_user_name, repo_data.repo_name, run_name, workflow_name, provider_name,
                         status, submitted_at,
                         [a.artifact_path for a in artifact_specs] if artifact_specs else None,
                         tag_name,
                         [a.app_name for a in app_specs] if app_specs else None)
        self.repo_data = repo_data
        self.runner_id = runner_id
        self.request_id = request_id
        self.image_name = image_name
        self.commands = commands
        self.env = env
        self.working_dir = working_dir
        self.artifact_specs = artifact_specs
        self.port_count = port_count
        self.ports = ports
        self.host_name = host_name
        self.requirements = requirements
        self.dep_specs = dep_specs
        self.master_job = master_job
        self.app_specs = app_specs

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]") if self.commands else None
        artifact_specs = ("[" + ", ".join(
            map(lambda a: _quoted(str(a)), self.artifact_specs)) + "]") if self.artifact_specs else None
        app_specs = ("[" + ", ".join(map(lambda a: str(a), self.app_specs)) + "]") if self.app_specs else None
        dep_specs = ("[" + ", ".join(map(lambda d: str(d), self.dep_specs)) + "]") if self.dep_specs else None
        return f'Job(job_id="{self.job_id}", repo_data={self.repo_data}, ' \
               f'run_name="{self.run_name}", workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{self.provider_name}", ' \
               f'status=JobStatus.{self.status.name}, ' \
               f'submitted_at={self.submitted_at}, ' \
               f'image_name="{self.image_name}", ' \
               f'commands={commands}, ' \
               f'env={self.env}, ' \
               f'working_dir={_quoted(self.working_dir)}, ' \
               f'port_count={self.port_count}, ' \
               f'ports={self.ports}, ' \
               f'host_name={_quoted(self.host_name)}, ' \
               f'artifact_specs={artifact_specs}, ' \
               f'requirements={self.requirements}, ' \
               f'dep_specs={dep_specs}, ' \
               f'master_job={self.master_job}, ' \
               f'app_specs={app_specs}, ' \
               f'runner_id={_quoted(self.runner_id)}, ' \
               f'request_id={_quoted(self.request_id)}, ' \
               f'tag_name={_quoted(self.tag_name)})'


class JobSpec(JobRef):
    def __init__(self, image_name: str, commands: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, working_dir: Optional[str] = None,
                 artifact_specs: Optional[List[ArtifactSpec]] = None,
                 port_count: Optional[int] = None,
                 requirements: Optional[Requirements] = None,
                 master_job: Optional[JobRef] = None, app_specs: Optional[List[AppSpec]] = None):
        self.job_id = None
        self.image_name = image_name
        self.commands = commands
        self.env = env
        self.working_dir = working_dir
        self.port_count = port_count
        self.artifact_specs = artifact_specs
        self.requirements = requirements
        self.master_job = master_job
        self.app_specs = app_specs

    def get_id(self) -> Optional[str]:
        return self.job_id

    def set_id(self, job_id: Optional[str]):
        self.job_id = job_id

    def __str__(self) -> str:
        commands = ("[" + ", ".join(map(lambda a: _quoted(str(a)), self.commands)) + "]") if self.commands else None
        artifact_specs = ("[" + ", ".join(
            map(lambda a: str(a), self.artifact_specs)) + "]") if self.artifact_specs else None
        app_specs = ("[" + ", ".join(map(lambda a: str(a), self.app_specs)) + "]") if self.app_specs else None
        return f'JobSpec(job_id="{self.job_id}", image_name="{self.image_name}", ' \
               f'commands={commands}, ' \
               f'env={self.env}, ' \
               f'working_dir={_quoted(self.working_dir)}, ' \
               f'port_count={self.port_count}, ' \
               f'artifact_specs={artifact_specs}, ' \
               f'requirements={self.requirements}, ' \
               f'master_job={self.master_job}, ' \
               f'app_specs={app_specs})'
