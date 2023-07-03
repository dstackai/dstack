from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator, List, Optional

import dstack._internal.core.build
from dstack._internal.backend.base import artifacts as base_artifacts
from dstack._internal.backend.base import build as base_build
from dstack._internal.backend.base import cache as base_cache
from dstack._internal.backend.base import jobs as base_jobs
from dstack._internal.backend.base import repos as base_repos
from dstack._internal.backend.base import runs as base_runs
from dstack._internal.backend.base import secrets as base_secrets
from dstack._internal.backend.base import tags as base_tags
from dstack._internal.backend.base.compute import Compute
from dstack._internal.backend.base.logs import Logging
from dstack._internal.backend.base.secrets import SecretsManager
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.artifact import Artifact
from dstack._internal.core.build import BuildPlan
from dstack._internal.core.instance import InstanceType
from dstack._internal.core.job import Job, JobHead, JobStatus
from dstack._internal.core.log_event import LogEvent
from dstack._internal.core.repo import RemoteRepoCredentials, RepoHead, RepoSpec
from dstack._internal.core.repo.base import Repo
from dstack._internal.core.run import RunHead
from dstack._internal.core.secret import Secret
from dstack._internal.core.tag import TagHead
from dstack._internal.utils.common import PathLike


class Backend(ABC):
    NAME = None

    @classmethod
    @abstractmethod
    def load(cls) -> Optional["Backend"]:
        pass

    @property
    def name(self) -> str:
        return self.NAME

    @abstractmethod
    def predict_instance_type(self, job: Job) -> Optional[InstanceType]:
        pass

    @abstractmethod
    def create_run(self, repo_id: str) -> str:
        pass

    @abstractmethod
    def create_job(self, job: Job):
        pass

    def submit_job(self, job: Job, failed_to_start_job_new_status: JobStatus = JobStatus.FAILED):
        self.create_job(job)
        self.run_job(job, failed_to_start_job_new_status)

    def resubmit_job(self, job: Job, failed_to_start_job_new_status: JobStatus = JobStatus.FAILED):
        base_jobs.update_job_submission(job)
        self.run_job(job, failed_to_start_job_new_status)

    @abstractmethod
    def get_job(self, repo_id: str, job_id: str) -> Optional[Job]:
        pass

    @abstractmethod
    def list_jobs(self, repo_id: str, run_name: str) -> List[Job]:
        pass

    @abstractmethod
    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        pass

    @abstractmethod
    def stop_job(self, repo_id: str, abort: bool, job_id: str):
        pass

    @abstractmethod
    def list_job_heads(self, repo_id: str, run_name: Optional[str] = None) -> List[JobHead]:
        pass

    @abstractmethod
    def delete_job_head(self, repo_id: str, job_id: str):
        pass

    @abstractmethod
    def list_run_heads(
        self,
        repo_id: str,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> List[RunHead]:
        pass

    def get_run_head(
        self,
        repo_id: str,
        run_name: str,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> Optional[RunHead]:
        run_heads_list = self.list_run_heads(
            repo_id=repo_id,
            run_name=run_name,
            include_request_heads=include_request_heads,
            interrupted_job_new_status=interrupted_job_new_status,
        )
        if len(run_heads_list) == 0:
            return None
        return run_heads_list[0]

    @abstractmethod
    def poll_logs(
        self,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        diagnose: bool = False,
    ) -> Generator[LogEvent, None, None]:
        pass

    @abstractmethod
    def list_run_artifact_files(
        self, repo_id: str, run_name: str, prefix: str, recursive: bool = False
    ) -> List[Artifact]:
        pass

    @abstractmethod
    def download_run_artifact_files(
        self,
        repo_id: str,
        run_name: str,
        output_dir: Optional[PathLike],
        files_path: Optional[PathLike] = None,
    ):
        pass

    @abstractmethod
    def upload_job_artifact_files(
        self,
        repo_id: str,
        job_id: str,
        artifact_name: str,
        artifact_path: PathLike,
        local_path: PathLike,
    ):
        pass

    @abstractmethod
    def list_tag_heads(self, repo_id: str) -> List[TagHead]:
        pass

    @abstractmethod
    def get_tag_head(self, repo_id: str, tag_name: str) -> Optional[TagHead]:
        pass

    @abstractmethod
    def add_tag_from_run(
        self, repo_id: str, tag_name: str, run_name: str, run_jobs: Optional[List[Job]]
    ):
        pass

    @abstractmethod
    def add_tag_from_local_dirs(
        self,
        repo: Repo,
        hub_user_name: str,
        tag_name: str,
        local_dirs: List[str],
        artifact_paths: List[str],
    ):
        pass

    @abstractmethod
    def delete_tag_head(self, repo_id: str, tag_head: TagHead):
        pass

    @abstractmethod
    def list_repo_heads(self) -> List[RepoHead]:
        pass

    @abstractmethod
    def update_repo_last_run_at(self, repo_spec: RepoSpec, last_run_at: int):
        pass

    @abstractmethod
    def get_repo_credentials(self, repo_id: str) -> Optional[RemoteRepoCredentials]:
        pass

    @abstractmethod
    def save_repo_credentials(self, repo_id: str, repo_credentials: RemoteRepoCredentials):
        pass

    @abstractmethod
    def delete_repo(self, repo_id: str):
        pass

    @abstractmethod
    def list_secret_names(self, repo_id: str) -> List[str]:
        pass

    @abstractmethod
    def get_secret(self, repo_id: str, secret_name: str) -> Optional[Secret]:
        pass

    @abstractmethod
    def add_secret(self, repo_id: str, secret: Secret):
        pass

    @abstractmethod
    def update_secret(self, repo_id: str, secret: Secret):
        pass

    @abstractmethod
    def delete_secret(self, repo_id: str, secret_name: str):
        pass

    @abstractmethod
    def delete_configuration_cache(
        self, repo_id: str, hub_user_name: str, configuration_path: str
    ):
        pass

    @abstractmethod
    def get_signed_download_url(self, object_key: str) -> str:
        pass

    @abstractmethod
    def get_signed_upload_url(self, object_key: str) -> str:
        pass

    @abstractmethod
    def predict_build_plan(self, job: Job) -> BuildPlan:
        pass


class ComponentBasedBackend(Backend):
    @abstractmethod
    def storage(self) -> Storage:
        pass

    @abstractmethod
    def compute(self) -> Compute:
        pass

    @abstractmethod
    def secrets_manager(self) -> SecretsManager:
        pass

    @abstractmethod
    def logging(self) -> Logging:
        pass

    def predict_instance_type(self, job: Job) -> Optional[InstanceType]:
        return base_jobs.predict_job_instance(self.compute(), job)

    def create_run(self, repo_id: str) -> str:
        return base_runs.create_run(self.storage())

    def create_job(self, job: Job):
        base_jobs.create_job(self.storage(), job)

    def get_job(self, repo_id: str, job_id: str) -> Optional[Job]:
        return base_jobs.get_job(self.storage(), repo_id, job_id)

    def list_jobs(self, repo_id: str, run_name: str) -> List[Job]:
        return base_jobs.list_jobs(self.storage(), repo_id, run_name)

    def run_job(self, job: Job, failed_to_start_job_new_status: JobStatus):
        self.predict_build_plan(job)  # raises exception on missing build
        base_jobs.run_job(self.storage(), self.compute(), job, failed_to_start_job_new_status)

    def stop_job(self, repo_id: str, abort: bool, job_id: str):
        base_jobs.stop_job(self.storage(), self.compute(), repo_id, job_id, abort)

    def list_job_heads(self, repo_id: str, run_name: Optional[str] = None) -> List[JobHead]:
        return base_jobs.list_job_heads(self.storage(), repo_id, run_name)

    def delete_job_head(self, repo_id: str, job_id: str):
        base_jobs.delete_job_head(self.storage(), repo_id, job_id)

    def list_run_heads(
        self,
        repo_id: str,
        run_name: Optional[str] = None,
        include_request_heads: bool = True,
        interrupted_job_new_status: JobStatus = JobStatus.FAILED,
    ) -> List[RunHead]:
        job_heads = self.list_job_heads(repo_id=repo_id, run_name=run_name)
        return base_runs.get_run_heads(
            self.storage(),
            self.compute(),
            job_heads,
            include_request_heads,
            interrupted_job_new_status,
        )

    def poll_logs(
        self,
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        descending: bool = False,
        diagnose: bool = False,
    ) -> Generator[LogEvent, None, None]:
        return self.logging().poll_logs(
            self.storage(),
            repo_id,
            run_name,
            start_time,
            end_time,
            descending,
            diagnose,
        )

    def list_run_artifact_files(
        self, repo_id: str, run_name: str, prefix: str, recursive: bool = False
    ) -> List[Artifact]:
        return base_artifacts.list_run_artifact_files(
            self.storage(), repo_id, run_name, prefix, recursive
        )

    def download_run_artifact_files(
        self,
        repo_id: str,
        run_name: str,
        output_dir: Optional[PathLike],
        files_path: Optional[PathLike] = None,
    ):
        artifacts = self.list_run_artifact_files(
            repo_id, run_name=run_name, prefix="", recursive=True
        )
        base_artifacts.download_run_artifact_files(
            storage=self.storage(),
            repo_id=repo_id,
            artifacts=artifacts,
            output_dir=output_dir,
            files_path=files_path,
        )

    def upload_job_artifact_files(
        self,
        repo_id: str,
        job_id: str,
        artifact_name: str,
        artifact_path: PathLike,
        local_path: PathLike,
    ):
        base_artifacts.upload_job_artifact_files(
            storage=self.storage(),
            repo_id=repo_id,
            job_id=job_id,
            artifact_name=artifact_name,
            artifact_path=artifact_path,
            local_path=local_path,
        )

    def list_tag_heads(self, repo_id: str) -> List[TagHead]:
        return base_tags.list_tag_heads(self.storage(), repo_id)

    def get_tag_head(self, repo_id: str, tag_name: str) -> Optional[TagHead]:
        return base_tags.get_tag_head(self.storage(), repo_id, tag_name)

    def add_tag_from_run(
        self, repo_id: str, tag_name: str, run_name: str, run_jobs: Optional[List[Job]]
    ):
        base_tags.create_tag_from_run(
            self.storage(),
            repo_id,
            tag_name,
            run_name,
            run_jobs,
        )

    def add_tag_from_local_dirs(
        self,
        repo: Repo,
        hub_user_name: str,
        tag_name: str,
        local_dirs: List[str],
        artifact_paths: List[str],
    ):
        base_tags.create_tag_from_local_dirs(
            storage=self.storage(),
            repo=repo,
            hub_user_name=hub_user_name,
            tag_name=tag_name,
            local_dirs=local_dirs,
            artifact_paths=artifact_paths,
        )

    def delete_tag_head(self, repo_id: str, tag_head: TagHead):
        base_tags.delete_tag(self.storage(), repo_id, tag_head)

    def list_repo_heads(self) -> List[RepoHead]:
        return base_repos.list_repo_heads(self.storage())

    def update_repo_last_run_at(self, repo_spec: RepoSpec, last_run_at: int):
        base_repos.update_repo_last_run_at(
            self.storage(),
            repo_spec,
            last_run_at,
        )

    def get_repo_credentials(self, repo_id: str) -> Optional[RemoteRepoCredentials]:
        return base_repos.get_repo_credentials(self.secrets_manager(), repo_id)

    def save_repo_credentials(self, repo_id: str, repo_credentials: RemoteRepoCredentials):
        base_repos.save_repo_credentials(self.secrets_manager(), repo_id, repo_credentials)

    def delete_repo(self, repo_id: str):
        base_repos.delete_repo(self.storage(), repo_id)

    def list_secret_names(self, repo_id: str) -> List[str]:
        return base_secrets.list_secret_names(self.storage(), repo_id)

    def get_secret(self, repo_id: str, secret_name: str) -> Optional[Secret]:
        return base_secrets.get_secret(self.secrets_manager(), repo_id, secret_name)

    def add_secret(self, repo_id: str, secret: Secret):
        base_secrets.add_secret(self.storage(), self.secrets_manager(), repo_id, secret)

    def update_secret(self, repo_id: str, secret: Secret):
        base_secrets.update_secret(self.storage(), self.secrets_manager(), repo_id, secret)

    def delete_secret(self, repo_id: str, secret_name: str):
        base_secrets.delete_secret(self.storage(), self.secrets_manager(), repo_id, secret_name)

    def get_signed_download_url(self, object_key: str) -> str:
        return self.storage().get_signed_download_url(object_key)

    def get_signed_upload_url(self, object_key: str) -> str:
        return self.storage().get_signed_upload_url(object_key)

    def delete_configuration_cache(
        self, repo_id: str, hub_user_name: str, configuration_path: str
    ):
        base_cache.delete_configuration_cache(
            self.storage(), repo_id, hub_user_name, configuration_path
        )

    def predict_build_plan(self, job: Job) -> BuildPlan:
        return base_build.predict_build_plan(
            self.storage(), job, dstack._internal.core.build.DockerPlatform.amd64
        )
