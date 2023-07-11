import copy
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional, Tuple

import dstack._internal.configurators as configurators
from dstack._internal.api.repos import get_local_repo_credentials
from dstack._internal.backend.base import artifacts as base_artifacts
from dstack._internal.core.artifact import Artifact
from dstack._internal.core.job import Job, JobHead, JobStatus
from dstack._internal.core.log_event import LogEvent
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.repo import RemoteRepoCredentials, Repo, RepoHead
from dstack._internal.core.repo.remote import RemoteRepo
from dstack._internal.core.run import RunHead
from dstack._internal.core.secret import Secret
from dstack._internal.core.tag import TagHead
from dstack._internal.hub.models import ProjectInfo
from dstack.api.hub._api_client import HubAPIClient
from dstack.api.hub._config import HubClientConfig
from dstack.api.hub._storage import HUBStorage
from dstack.api.hub.errors import HubClientError


class HubClient:
    def __init__(
        self,
        config: HubClientConfig,
        project: Optional[str] = None,
        repo: Optional[Repo] = None,
        repo_credentials: Optional[RemoteRepoCredentials] = None,
        auto_init: bool = False,
    ):
        self.project = project
        self.repo = repo
        self._repo_credentials = repo_credentials
        self._auto_init = auto_init
        self._client_config = config
        self._api_client = HubAPIClient(
            url=self._client_config.url,
            token=self._client_config.token,
            project=self.project,
            repo=self.repo,
        )
        self._storage = HUBStorage(self._api_client)

    @staticmethod
    def validate_config(config: HubClientConfig, project: str):
        project_info = HubAPIClient(
            url=config.url, token=config.token, project=project, repo=None
        ).get_project_info()
        if project_info.backend.__root__.type == "local":
            hostname = urllib.parse.urlparse(config.url).hostname
            if hostname not in ["localhost", "127.0.0.1"]:
                raise HubClientError(
                    "Projects with local backend hosted on remote Hub are not yet supported. "
                    "Consider starting Hub locally if you need to use local backend."
                )

    def get_project_backend_type(self) -> str:
        return self._get_project_info().backend.__root__.type

    def _get_project_info(self) -> ProjectInfo:
        return self._api_client.get_project_info()

    def create_run(self) -> str:
        return self._api_client.create_run()

    def create_job(self, job: Job):
        self._api_client.create_job(job=job)

    def submit_job(self, job: Job, failed_to_start_job_new_status: JobStatus = JobStatus.FAILED):
        self.create_job(job)
        self.run_job(job, failed_to_start_job_new_status)

    def get_job(self, job_id: str, repo_id: Optional[str] = None) -> Optional[Job]:
        return self._api_client.get_job(job_id=job_id)

    def list_jobs(self, run_name: str, repo_id: Optional[str] = None) -> List[Job]:
        return self._api_client.list_jobs(run_name=run_name)

    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        self._api_client.run_job(job=job)

    def stop_job(self, job_id: str, abort: bool):
        self._api_client.stop_job(job_id=job_id, abort=abort)

    def stop_jobs(self, run_name: Optional[str], abort: bool):
        job_heads = self.list_job_heads(run_name)
        for job_head in job_heads:
            if job_head.status.is_unfinished():
                self.stop_job(job_head.job_id, abort)

    def list_job_heads(
        self, run_name: Optional[str] = None, repo_id: Optional[str] = None
    ) -> List[JobHead]:
        return self._api_client.list_job_heads(run_name=run_name)

    def delete_job_head(self, job_id: str, repo_id: Optional[str] = None):
        self._api_client.delete_job_head(job_id=job_id)

    def delete_job_heads(self, run_name: Optional[str]):
        job_heads = []
        for job_head in self.list_job_heads(run_name):
            if job_head.status.is_finished():
                job_heads.append(job_head)
            else:
                if run_name:
                    sys.exit("The run is not finished yet. Stop the run first.")
        for job_head in job_heads:
            self.delete_job_head(job_head.job_id)

    def list_run_heads(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
        repo_id: Optional[str] = None,
    ) -> List[RunHead]:
        return self._api_client.list_run_heads(
            run_name=run_name,
            include_request_heads=include_request_heads,
        )

    def poll_logs(
        self,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        diagnose: bool = False,
        repo_id: Optional[str] = None,
    ) -> Generator[LogEvent, None, None]:
        # /{hub_name}/logs/poll
        return self._api_client.poll_logs(
            run_name=run_name,
            start_time=start_time,
            end_time=end_time,
            descending=descending,
            diagnose=diagnose,
        )

    def list_run_artifact_files(
        self,
        run_name: str,
        prefix: str = "",
        recursive: bool = False,
        repo_id: Optional[str] = None,
    ) -> List[Artifact]:
        # /{hub_name}/artifacts/list
        return self._api_client.list_run_artifact_files(
            run_name=run_name, prefix=prefix, recursive=recursive
        )

    def download_run_artifact_files(
        self,
        run_name: str,
        output_dir: Optional[str],
        files_path: Optional[str] = None,
    ):
        # /{hub_name}/artifacts/download
        artifacts = self.list_run_artifact_files(run_name=run_name, recursive=True)
        base_artifacts.download_run_artifact_files(
            storage=self._storage,
            repo_id=self.repo.repo_id,
            artifacts=artifacts,
            output_dir=output_dir,
            files_path=files_path,
        )

    def upload_job_artifact_files(
        self,
        job_id: str,
        artifact_name: str,
        artifact_path: str,
        local_path: Path,
    ):
        # /{hub_name}/artifacts/upload
        base_artifacts.upload_job_artifact_files(
            storage=self._storage,
            repo_id=self.repo.repo_id,
            job_id=job_id,
            artifact_name=artifact_name,
            artifact_path=artifact_path,
            local_path=local_path,
        )

    def list_tag_heads(self) -> List[TagHead]:
        return self._api_client.list_tag_heads()

    def get_tag_head(self, tag_name: str) -> Optional[TagHead]:
        return self._api_client.get_tag_head(tag_name=tag_name)

    def add_tag_from_run(
        self,
        tag_name: str,
        run_name: str,
        run_jobs: Optional[List[Job]],
    ):
        return self._api_client.add_tag_from_run(
            tag_name=tag_name, run_name=run_name, run_jobs=run_jobs
        )

    def add_tag_from_local_dirs(self, tag_name: str, local_dirs: List[str]):
        # /{hub_name}/tags/add
        return self._api_client.add_tag_from_local_dirs(tag_name=tag_name, local_dirs=local_dirs)

    def delete_tag_head(self, tag_head: TagHead):
        # /{hub_name}/tags/delete
        return self._api_client.delete_tag_head(tag_head=tag_head)

    def update_repo_last_run_at(self, last_run_at: int):
        # /{hub_name}/repos/update
        return self._api_client.update_repo_last_run_at(last_run_at=last_run_at)

    def list_repo_heads(self) -> List[RepoHead]:
        return self._api_client.list_repo_heads()

    def _get_repo_credentials(self) -> Optional[RemoteRepoCredentials]:
        return self._api_client.get_repos_credentials()

    def get_repo_credentials(self) -> Optional[RemoteRepoCredentials]:
        credentials = self._get_repo_credentials()
        if credentials is None:
            if not self._auto_init:
                return None  # todo raise?
            elif self._repo_credentials is not None:
                credentials = self._repo_credentials
            else:
                if isinstance(self.repo, RemoteRepo):
                    credentials = get_local_repo_credentials(self.repo.repo_data)
            self.save_repo_credentials(credentials)
        return credentials

    def save_repo_credentials(self, repo_credentials: RemoteRepoCredentials):
        self._api_client.save_repos_credentials(repo_credentials=repo_credentials)

    def list_secret_names(self) -> List[str]:
        return self._api_client.list_secret_names()

    def get_secret(self, secret_name: str) -> Optional[Secret]:
        return self._api_client.get_secret(secret_name=secret_name)

    def add_secret(self, secret: Secret):
        self._api_client.add_secret(secret=secret)

    def update_secret(self, secret: Secret):
        self._api_client.update_secret(secret=secret)

    def delete_secret(self, secret_name: str):
        # /{hub_name}/secrets/delete
        self._api_client.delete_secret(secret_name=secret_name)

    def delete_configuration_cache(self, configuration_path: str):
        self._api_client.delete_configuration_cache(configuration_path=configuration_path)

    def get_run_plan(self, configurator: "configurators.JobConfigurator") -> RunPlan:
        """
        :param configurator: args must be already applied
        :return: run plan
        """
        jobs = configurator.get_jobs(
            repo=self.repo, run_name="dry-run", repo_code_filename="", ssh_key_pub=""
        )
        run_plan = self._api_client.get_run_plan(jobs)
        return run_plan

    def run_configuration(
        self,
        configurator: "configurators.JobConfigurator",
        ssh_key_pub: str,
        run_args: Optional[List[str]] = None,
    ) -> Tuple[str, List[Job]]:
        run_name = self.create_run()
        configurator = copy.deepcopy(configurator)
        configurator.inject_context(
            {"run": {"name": run_name, "args": configurator.join_run_args(run_args)}}
        )

        # todo handle tag_name & dependencies

        repo_code_filename = self._upload_code_file()
        jobs = configurator.get_jobs(
            repo=self.repo,
            run_name=run_name,
            repo_code_filename=repo_code_filename,
            ssh_key_pub=ssh_key_pub,
        )
        for job in jobs:
            self.submit_job(job)
        self.update_repo_last_run_at(last_run_at=int(round(time.time() * 1000)))
        return run_name, jobs

    def _upload_code_file(self) -> str:
        with tempfile.NamedTemporaryFile("w+b") as f:
            repo_code_filename = self.repo.repo_data.write_code_file(f)
            f.seek(0)
            self._storage.upload_file(f.name, repo_code_filename, lambda _: ...)
        return repo_code_filename
