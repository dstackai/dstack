import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional, Generator, Tuple, Dict

from dstack.core.app import AppSpec
from dstack.core.repo import RepoData, RepoCredentials, RepoAddress, RepoHead
from dstack.core.job import Job, JobHead
from dstack.core.secret import Secret
from dstack.core.log_event import LogEvent
from dstack.core.tag import TagHead
from dstack.core.run import RunHead
from dstack.core.runners import Runner


class BackendType(Enum):
    REMOTE = "remote"
    LOCAL = "local"

    def __str__(self):
        return str(self.value)


class Backend(object):
    NAME = "name the backend"
    _loaded = False

    @property
    def name(self) -> str:
        return self.NAME

    def configure(self):
        pass

    def create_run(self, repo_address: RepoAddress) -> str:
        pass

    def submit_job(self, job: Job, counter: List[int]):
        pass

    def get_job(self, repo_address: RepoAddress, job_id: str) -> Optional[Job]:
        pass

    def list_job_heads(
        self, repo_address: RepoAddress, run_name: Optional[str] = None
    ) -> List[JobHead]:
        pass

    def list_jobs(self, repo_address: RepoAddress, run_name: str) -> List[Job]:
        pass

    def run_job(self, job: Job) -> Runner:
        pass

    def stop_job(self, repo_address: RepoAddress, job_id: str, abort: bool):
        pass

    def delete_job_head(self, repo_address: RepoAddress, job_id: str):
        pass

    def store_job(self, job: Job):
        pass

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
        pass

    def get_run_heads(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        include_request_heads: bool = True,
    ) -> List[RunHead]:
        pass

    def poll_logs(
        self,
        repo_address: RepoAddress,
        job_heads: List[JobHead],
        start_time: int,
        attached: bool,
    ) -> Generator[LogEvent, None, None]:
        pass

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

    def download_run_artifact_files(
        self,
        repo_address: RepoAddress,
        run_name: str,
        output_dir: Optional[str],
        output_job_dirs: bool = True,
    ):
        pass

    def upload_job_artifact_files(
        self,
        repo_address: RepoAddress,
        job_id: str,
        artifact_name: str,
        local_path: Path,
    ):
        pass

    def list_run_artifact_files(
        self, repo_address: RepoAddress, run_name: str
    ) -> Generator[Tuple[str, str, str, int], None, None]:
        pass

    def list_tag_heads(self, repo_address: RepoAddress) -> List[TagHead]:
        pass

    def get_tag_head(self, repo_address: RepoAddress, tag_name: str) -> Optional[TagHead]:
        pass

    def add_tag_from_run(
        self,
        repo_address: RepoAddress,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        pass

    def add_tag_from_local_dirs(self, repo_data: RepoData, tag_name: str, local_dirs: List[str]):
        pass

    def delete_tag_head(self, repo_address: RepoAddress, tag_head: TagHead):
        pass

    def list_repo_heads(self) -> List[RepoHead]:
        pass

    def update_repo_last_run_at(self, repo_address: RepoAddress, last_run_at: int):
        pass

    def increment_repo_tags_count(self, repo_address: RepoAddress):
        pass

    def decrement_repo_tags_count(self, repo_address: RepoAddress):
        pass

    def delete_repo(self, repo_address: RepoAddress):
        pass

    def get_repo_credentials(self, repo_address: RepoAddress) -> Optional[RepoCredentials]:
        pass

    def save_repo_credentials(self, repo_address: RepoAddress, repo_credentials: RepoCredentials):
        pass

    def list_run_artifact_files_and_folders(
        self, repo_address: RepoAddress, job_id: str, path: str
    ) -> List[Tuple[str, bool]]:
        pass

    def list_secret_names(self, repo_address: RepoAddress) -> List[str]:
        pass

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        pass

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        pass

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        ...

    def loaded(self):
        return self._loaded

    def type(self) -> BackendType:
        ...
