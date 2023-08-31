import copy
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import dstack._internal.configurators as configurators
from dstack._internal.api.repos import get_local_repo_credentials
from dstack._internal.backend.base import artifacts as base_artifacts
from dstack._internal.core.artifact import Artifact
from dstack._internal.core.gateway import Gateway, GatewayBackend
from dstack._internal.core.job import Job, JobHead, JobStatus
from dstack._internal.core.log_event import LogEvent
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.repo import RemoteRepoCredentials, Repo, RepoHead
from dstack._internal.core.repo.remote import RemoteRepo
from dstack._internal.core.secret import Secret
from dstack._internal.core.tag import TagHead
from dstack._internal.hub.schemas import BackendInfo, RunInfo
from dstack.api.hub._api_client import HubAPIClient
from dstack.api.hub._config import HubClientConfig
from dstack.api.hub._storage import HUBStorage
from dstack.api.hub.errors import HubClientError


class HubClient:
    def __init__(
        self,
        config: HubClientConfig,
        repo: Repo,
        project: str,
        repo_credentials: Optional[RemoteRepoCredentials] = None,
        auto_init: bool = False,
    ):
        self.project = project
        self.repo = repo
        self.client_config = config
        self._repo_credentials = repo_credentials
        self._auto_init = auto_init
        self._api_client = HubAPIClient(
            url=self.client_config.url,
            token=self.client_config.token,
            project=self.project,
            repo=self.repo,
        )
        self._storage = HUBStorage(self._api_client)

    @staticmethod
    def validate_config(config: HubClientConfig, project: str):
        HubAPIClient(
            url=config.url, token=config.token, project=project, repo=None
        ).get_project_info()

    def list_backends(self) -> List[BackendInfo]:
        return self._api_client.list_backends()

    def create_run(self, run_name: Optional[str]) -> str:
        return self._api_client.create_run(run_name)

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._api_client.get_job(job_id=job_id)

    def list_jobs(self, run_name: str) -> List[Job]:
        return self._api_client.list_jobs(run_name=run_name)

    def run_job(self, job: Job):
        self._api_client.run_job(job=job)

    def restart_job(self, job: Job):
        self._api_client.restart_job(job)

    def list_job_heads(self, run_name: Optional[str] = None) -> List[JobHead]:
        return self._api_client.list_job_heads(run_name=run_name)

    def list_runs(
        self,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
    ) -> List[RunInfo]:
        return self._api_client.list_runs(
            run_name=run_name,
            include_request_heads=include_request_heads,
        )

    def delete_run(self, run_name: str):
        self._api_client.delete_runs([run_name])

    def stop_run(self, run_name: str, terminate: bool, abort: bool):
        self._api_client.stop_runs(run_names=[run_name], terminate=terminate, abort=abort)

    def poll_logs(
        self,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        diagnose: bool = False,
    ) -> Generator[LogEvent, None, None]:
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
    ) -> List[Artifact]:
        return self._api_client.list_run_artifact_files(
            run_name=run_name, prefix=prefix, recursive=recursive
        )

    def download_run_artifact_files(
        self,
        run_name: str,
        output_dir: Optional[str],
        files_path: Optional[str] = None,
    ):
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
        return self._api_client.add_tag_from_local_dirs(tag_name=tag_name, local_dirs=local_dirs)

    def delete_tag_head(self, tag_head: TagHead):
        return self._api_client.delete_tag_head(tag_head=tag_head)

    def update_repo_last_run_at(self, last_run_at: int):
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
        self._api_client.delete_secret(secret_name=secret_name)

    def delete_configuration_cache(self, configuration_path: str):
        self._api_client.delete_configuration_cache(configuration_path=configuration_path)

    def get_run_plan(self, configurator: "configurators.JobConfigurator") -> RunPlan:
        """
        :param configurator: args must be already applied
        :return: run plan
        """
        jobs = configurator.get_jobs(
            repo=self.repo,
            run_name="dry-run",
            repo_code_filename="",
            ssh_key_pub="",
        )
        run_plan = self._api_client.get_run_plan(jobs)
        return run_plan

    def run_configuration(
        self,
        configurator: "configurators.JobConfigurator",
        ssh_key_pub: str,
        run_name: Optional[str] = None,
        run_args: Optional[List[str]] = None,
        run_plan: Optional[RunPlan] = None,
    ) -> Tuple[str, List[Job]]:
        run_name = self.create_run(run_name)
        configurator = copy.deepcopy(configurator)
        configurator.inject_context(
            {"run": {"name": run_name, "args": configurator.join_run_args(run_args)}}
        )

        # Todo handle tag_name & dependencies

        with tempfile.NamedTemporaryFile("w+b") as f:
            repo_code_filename = self.repo.repo_data.write_code_file(f)
            jobs = configurator.get_jobs(
                repo=self.repo,
                run_name=run_name,
                repo_code_filename=repo_code_filename,
                ssh_key_pub=ssh_key_pub,
                run_plan=run_plan,
            )
            # We upload code patch to all backends since we don't know which one will be used.
            # This can be optimized if we upload to the server first.
            considered_backends = jobs[0].backends or [b.name for b in self.list_backends()]
            with ThreadPoolExecutor(max_workers=4) as executor:
                for backend in considered_backends:
                    executor.submit(
                        self._storage.upload_file,
                        backend,
                        f.name,
                        repo_code_filename,
                        lambda _: ...,
                    )
            for job in jobs:
                self.run_job(job)
        self.update_repo_last_run_at(last_run_at=int(round(time.time() * 1000)))
        return run_name, jobs

    def create_gateway(self, backend: str, region: str) -> Gateway:
        return self._api_client.create_gateway(backend=backend, region=region)

    def get_gateway_backends(self) -> List[GatewayBackend]:
        return self._api_client.get_gateway_backends()

    def list_gateways(self) -> List[Gateway]:
        return self._api_client.list_gateways()

    def delete_gateway(self, instance_name: str):
        self._api_client.delete_gateway(instance_name)
