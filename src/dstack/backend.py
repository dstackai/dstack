import os
from abc import ABC
from enum import Enum
from typing import List, Optional, Generator, Tuple

from dstack.jobs import Job, JobStatus, JobHead
from dstack.repo import Repo
from dstack.runners import Resources, Runner
from dstack.util import _quoted
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


class LogEventSource(Enum):
    STDOUT = "stdout"
    STDERR = "stderr"


class LogEvent:
    def __init__(self, timestamp: int, job_id: Optional[str], log_message: str, log_source: LogEventSource):
        self.timestamp = timestamp
        self.job_id = job_id
        self.log_message = log_message
        self.log_source = log_source


class BackendError(Exception):
    def __init__(self, message: str):
        self.message = message


class TagHead:
    def __init__(self, repo_user_name: str, repo_name: str, tag_name: str, run_name: str,
                 workflow_name: Optional[str], provider_name: Optional[str], created_at: int,
                 artifacts: Optional[List[str]]):
        self.repo_user_name = repo_user_name
        self.repo_name = repo_name
        self.tag_name = tag_name
        self.run_name = run_name
        self.workflow_name = workflow_name
        self.provider_name = provider_name
        self.created_at = created_at
        self.artifacts = artifacts

    def __str__(self) -> str:
        return f'TagHead(repo_user_name="{self.repo_user_name}", ' \
               f'repo_name="{self.repo_name}", ' \
               f'tag_name="{self.tag_name}", ' \
               f'run_name="{self.run_name}", ' \
               f'workflow_name={_quoted(self.workflow_name)}, ' \
               f'provider_name="{_quoted(self.provider_name)}", ' \
               f'created_at={self.created_at}, ' \
               f'artifacts={("[" + ", ".join(map(lambda a: _quoted(str(a)), self.artifacts)) + "]") if self.artifacts else None})'


class Backend(ABC):
    def create_run(self, repo_user_name: str, repo_name: str) -> str:
        pass

    def submit_job(self, job: Job, counter: List[int]):
        pass

    def get_job(self, repo_user_name: str, repo_name: str, job_id: str) -> Job:
        pass

    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None) -> List[JobHead]:
        pass

    def run_job(self, job: Job) -> Runner:
        pass

    def stop_job(self, repo_user_name: str, repo_name: str, job_id: str, abort: bool):
        pass

    def stop_jobs(self, repo_user_name: str, repo_name: str, run_name: Optional[str], abort: bool):
        job_heads = self.get_job_heads(repo_user_name, repo_name, run_name)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(repo_user_name, repo_name, job_head.get_id(), abort)

    def get_runs(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None) -> List[Run]:
        runs_by_id = {}
        job_heads = self.get_job_heads(repo_user_name, repo_name, run_name)
        for job_head in job_heads:
            run_id = ','.join([job_head.run_name, job_head.workflow_name or ''])
            if run_id not in runs_by_id:
                run = Run(repo_user_name, repo_name, job_head.run_name, job_head.workflow_name, job_head.provider_name,
                          job_head.artifacts or [], job_head.status, job_head.submitted_at, job_head.tag_name)
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

    def poll_logs(self, repo_user_name: str, repo_name: str, run_name: str, start_time: int,
                  attached: bool) -> Generator[LogEvent, None, None]:
        pass

    def download_run_artifact_files(self, repo_user_name: str, repo_name: str, run_name: str,
                                    output_dir: Optional[str]):
        pass

    def list_run_artifact_files(self, repo_user_name: str, repo_name: str, run_name: str) -> List[Tuple[str, str, int]]:
        pass

    def get_tag_heads(self, repo_user_name: str, repo_name: str) -> List[TagHead]:
        pass

    def get_tag_head(self, repo_user_name: str, repo_name: str, tag_name: str) -> Optional[TagHead]:
        pass

    def create_tag_from_run(self, repo_user_name: str, repo_name: str, tag_name: str, run_name: str):
        pass

    def create_tag_from_local_dirs(self, repo: Repo, tag_name: str, local_dirs: List[str]):
        pass

    def delete_tag(self, repo_user_name: str, repo_name: str, tag_head: TagHead):
        pass


def load_backend() -> Backend:
    config = load_config()
    if isinstance(config.backend_config, AwsBackendConfig):
        from dstack.aws import AwsBackend

        return AwsBackend(config.backend_config)
    else:
        raise Exception(f"Unsupported backend: {config.backend_config}")
