import sys
from pathlib import Path
from typing import List, Optional, Generator, Dict, Tuple

from dstack.backend.local import (
    jobs,
    runs,
    tags,
    runners,
    repos,
    secrets,
    logs,
    artifacts,
)
from dstack.backend.local.config import LocalConfig
from dstack.backend import Backend, BackendType
from dstack.core.app import AppSpec
from dstack.core.repo import RepoData, RepoAddress, RepoHead, RepoCredentials
from dstack.core.job import Job, JobHead
from dstack.core.run import RunHead
from dstack.core.log_event import LogEvent
from dstack.core.tag import TagHead
from dstack.core.secret import Secret


class LocalBackend(Backend):
    NAME = "local"

    def __init__(self):
        self.backend_config = LocalConfig()
        self.backend_config.load()
        self._loaded = True

    def configure(self):
        pass

    def create_run(self, repo_address: RepoAddress) -> str:
        return runs.create_run(self.backend_config.path, repo_address)

    def submit_job(self, job: Job, counter: List[int]):
        jobs.create_job(self.backend_config.path, job, counter)
        runners.run_job(self.backend_config.path, job)

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        return jobs.get_job(self.backend_config.path, repo_address, job_id)

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        return jobs.list_job_heads(self.backend_config.path, repo_address, run_name)

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        return jobs.list_jobs(self.backend_config.path, repo_address, run_name)

    def run_job(self, job: Job):
        runners.run_job(self.backend_config.path, job)

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        runners.stop_job(self.backend_config.path, repo_address, job_id, abort)

    def store_job(self, job: Job):
        jobs.store_job(self.backend_config.path, job)

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        jobs.delete_job_head(self.backend_config.path, repo_address, job_id)

    def stop_jobs(self, repo_address: RepoAddress, run_name: Optional[str], abort: bool):
        job_heads = self.list_job_heads(repo_address, run_name)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(repo_address, job_head.job_id, abort)

    def delete_job_heads(self, repo_address: RepoAddress, run_name: Optional[str]):
        job_heads = []
        for job_head in self.list_job_heads(repo_address, run_name):
            if job_head.status.is_finished():
                job_heads.append(job_head)
            else:
                if run_name:
                    sys.exit("The run is not finished yet. Stop the run first.")

        for job_head in job_heads:
            self.delete_job_head(repo_address, job_head.job_id)

    def list_run_heads(
        self,
        repo_address: RepoAddress,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        return runs.list_run_heads(
            self.backend_config.path, repo_address, run_name, include_request_heads
        )

    def get_run_heads(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        return runs.get_run_heads(self.backend_config.path, job_heads, include_request_heads)

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        return logs.poll_logs(
            self.backend_config.path, repo_address, job_heads, start_time, attached
        )

    def query_logs(
        self,
        repo_address: RepoAddress,
        run_name: str,
        start_time: int,
        end_time: Optional[int],
        next_token: Optional[str],
        job_host_names: Dict[str, Optional[str]],
        job_ports: Dict[str, Optional[List[int]]],
        job_app_specs: Dict[str, Optional[List[AppSpec]]],
    ) -> Tuple[
        List[LogEvent],
        Optional[str],
        Dict[str, Optional[str]],
        Dict[str, Optional[List[int]]],
        Dict[str, Optional[List[AppSpec]]],
    ]:
        pass

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Tuple[str, str, int], None, None]:
        return artifacts.list_run_artifact_files(self.backend_config.path, repo_address, run_name)

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        return tags.list_tag_heads(self.backend_config.path, repo_address)

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        return tags.get_tag_head(self.backend_config.path, repo_address, tag_name)

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        tags.create_tag_from_run(
            self.backend_config.path,
            repo_address,
            tag_name,
            run_name,
            run_jobs,
        )

    def add_tag_from_local_dirs(self, repo_data: RepoData, tag_name: str, local_dirs: List[str]):
        tags.create_tag_from_local_dirs(
            self.backend_config.path,
            repo_data,
            tag_name,
            local_dirs,
        )

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        tags.delete_tag(self.backend_config.path, repo_address, tag_head)

    def list_repo_heads(self) -> List[RepoHead]:
        return repos.list_repo_heads(self.backend_config.path)

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        repos.update_repo_last_run_at(self.backend_config.path, repo_address, last_run_at)

    def increment_repo_tags_count(self, repo_address: RepoAddress):
        repos.increment_repo_tags_count(self.backend_config.path, repo_address)

    def decrement_repo_tags_count(self, repo_address: RepoAddress):
        repos.decrement_repo_tags_count(self.backend_config.path, repo_address)

    def delete_repo(self, repo_address: RepoAddress):
        repos.delete_repo(self.backend_config.path, repo_address)

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        return repos.get_repo_credentials(self.backend_config.path, repo_address)

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        repos.save_repo_credentials(self.backend_config.path, repo_address, repo_credentials)

    def list_run_artifact_files_and_folders(
        self, repo_address: RepoAddress, job_id: str, path: str
    ) -> List[Tuple[str, bool]]:
        return artifacts.list_run_artifact_files_and_folders(
            self.backend_config.path, repo_address, job_id, path
        )

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        return secrets.list_secret_names(self.backend_config.path, repo_address)

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        return secrets.get_secret(self.backend_config.path, repo_address, secret_name)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.add_secret(self.backend_config.path, repo_address, secret)

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        return secrets.update_secret(self.backend_config.path, repo_address, secret)

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        return secrets.remove_secret(self.backend_config.path, repo_address, secret_name)

    def type(self) -> BackendType:
        return BackendType.LOCAL

    def get_artifacts_path(self, repo_address: RepoAddress) -> Path:
        return artifacts.get_artifacts_path(self.backend_config.path, repo_address)
