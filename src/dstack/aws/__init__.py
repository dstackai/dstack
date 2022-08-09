import boto3
from botocore.client import BaseClient

from dstack.aws import logs, artifacts, jobs, run_names, runs, runners
from dstack.backend import *
from dstack.config import AwsBackendConfig


class AwsBackend(Backend):
    def __init__(self, backend_config: AwsBackendConfig):
        self.backend_config = backend_config

    def _s3_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("s3")

    def _ec2_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("ec2")

    def _iam_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("iam")

    def _logs_client(self) -> BaseClient:
        session = boto3.Session(profile_name=self.backend_config.profile_name,
                                region_name=self.backend_config.region_name)
        return session.client("logs")

    def create_run(self, repo_user_name: str, repo_name: str) -> str:
        return runs.create_run(self._s3_client(), self._logs_client(), self.backend_config.bucket_name,
                               repo_user_name, repo_name)

    # noinspection PyDefaultArgument
    def submit_job(self, job: Job, counter: List[int] = []):
        jobs.create_job(self._s3_client(), self.backend_config.bucket_name, job)
        runners.run_job(self._ec2_client(), self._iam_client(), self._s3_client(), self.backend_config.bucket_name,
                        self.backend_config.region_name, job)

    # noinspection PyDefaultArgument
    def get_job(self, repo_user_name: str, repo_name: str, job_id: str) -> Job:
        return jobs.get_job(self._s3_client(), self.backend_config.bucket_name, repo_user_name, repo_name, job_id)

    def get_job_heads(self, repo_user_name: str, repo_name: str, run_name: Optional[str] = None):
        return jobs.get_job_heads(self._s3_client(), self.backend_config.bucket_name, repo_user_name, repo_name,
                                  run_name)

    def run_job(self, job: Job) -> Runner:
        return runners.run_job(self._s3_client(), self.backend_config.bucket_name, job)

    def stop_job(self, repo_user_name: str, repo_name: str, job_id: str, abort: bool):
        job = self.get_job(repo_user_name, repo_name, job_id)
        runners.stop_job(self._ec2_client(), self._s3_client(), self.backend_config.bucket_name, job, abort)

    def poll_logs(self, repo_user_name: str, repo_name: str, run_name: str, start_time: int, attached: bool) -> \
            Generator[LogEvent, None, None]:
        return logs.poll_logs(self._s3_client(), self._logs_client(), self.backend_config.bucket_name, repo_user_name,
                              repo_name, run_name, start_time, attached)

    def _download_job_artifact_files(self, repo_user_name: str, repo_name: str, job_id: str, artifact_name: str,
                                     output_dir: Optional[str]):
        return artifacts.download_job_artifact_files(self._s3_client(), self.backend_config.bucket_name,
                                                     repo_user_name, repo_name, job_id, artifact_name, output_dir)

    def _list_job_artifact_files(self, repo_user_name: str, repo_name: str,
                                 job_id: str, artifact_name: str) -> List[Tuple[str, int]]:
        return artifacts.list_job_artifact_files(self._s3_client(), self.backend_config.bucket_name,
                                                 repo_user_name, repo_name, job_id, artifact_name)
