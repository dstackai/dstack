from typing import BinaryIO, Dict, Optional, Union

import requests
import requests.exceptions

from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import ClusterInfo, JobSpec, RunSpec
from dstack._internal.server.schemas.runner import (
    DockerImageBody,
    HealthcheckResponse,
    PullBody,
    PullResponse,
    StopBody,
    SubmitBody,
)

REMOTE_SHIM_PORT = 10998
REMOTE_RUNNER_PORT = 10999


class RunnerClient:
    def __init__(
        self,
        port: int,
        hostname: str = "localhost",
    ):
        self.secure = False
        self.hostname = hostname
        self.port = port

    def healthcheck(self) -> Optional[HealthcheckResponse]:
        try:
            resp = requests.get(self._url("/api/healthcheck"))
            resp.raise_for_status()
            return HealthcheckResponse.__response__.parse_obj(resp.json())
        except requests.exceptions.RequestException:
            return None

    def submit_job(
        self,
        run_spec: RunSpec,
        job_spec: JobSpec,
        cluster_info: ClusterInfo,
        secrets: Dict[str, str],
        repo_credentials: Optional[RemoteRepoCreds],
    ):
        body = SubmitBody(
            run_spec=run_spec,
            job_spec=job_spec,
            cluster_info=cluster_info,
            secrets=secrets,
            repo_credentials=repo_credentials,
        )
        resp = requests.post(
            # use .json() to encode enums
            self._url("/api/submit"),
            data=body.json(),
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

    def upload_code(self, file: Union[BinaryIO, bytes]):
        resp = requests.post(self._url("/api/upload_code"), data=file)
        resp.raise_for_status()

    def run_job(self):
        resp = requests.post(self._url("/api/run"))
        resp.raise_for_status()

    def pull(self, timestamp: int, timeout: int = 5) -> PullResponse:
        resp = requests.get(
            self._url("/api/pull"), params={"timestamp": timestamp}, timeout=timeout
        )
        resp.raise_for_status()
        return PullResponse.__response__.parse_obj(resp.json())

    def stop(self):
        resp = requests.post(self._url("/api/stop"))
        resp.raise_for_status()

    def _url(self, path: str) -> str:
        return f"{'https' if self.secure else 'http'}://{self.hostname}:{self.port}/{path.lstrip('/')}"


class ShimClient:
    def __init__(
        self,
        port: int,
        hostname: str = "localhost",
    ):
        self.secure = False
        self.hostname = hostname
        self.port = port

    def healthcheck(self, unmask_exeptions: bool = False) -> Optional[HealthcheckResponse]:
        try:
            resp = requests.get(self._url("/api/healthcheck"))
            resp.raise_for_status()
            return HealthcheckResponse.__response__.parse_obj(resp.json())
        except requests.exceptions.RequestException:
            if unmask_exeptions:
                raise
            return None

    def submit(
        self,
        username: str,
        password: str,
        image_name: str,
        container_name: str,
        shm_size: Optional[Memory],
    ):
        _shm_size = int(shm_size * 1024 * 1024 * 1014) if shm_size else 0
        post_body = DockerImageBody(
            username=username,
            password=password,
            image_name=image_name,
            container_name=container_name,
            shm_size=_shm_size,
        ).dict()
        resp = requests.post(
            self._url("/api/submit"),
            json=post_body,
        )
        resp.raise_for_status()

    def stop(self, force: bool = False):
        body = StopBody(force=force)
        resp = requests.post(self._url("/api/stop"), json=body.dict())
        resp.raise_for_status()

    def pull(self) -> PullBody:
        resp = requests.get(self._url("/api/pull"))
        resp.raise_for_status()
        return PullBody.__response__.parse_obj(resp.json())

    def _url(self, path: str) -> str:
        return f"{'https' if self.secure else 'http'}://{self.hostname}:{self.port}/{path.lstrip('/')}"
