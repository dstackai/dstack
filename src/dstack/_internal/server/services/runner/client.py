from dataclasses import dataclass
from typing import BinaryIO, Dict, List, Optional, Union

import requests
import requests.exceptions

from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import ClusterInfo, JobSpec, RunSpec
from dstack._internal.core.models.volumes import Volume, VolumeMountPoint
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    PullBody,
    PullResponse,
    ShimVolumeInfo,
    StopBody,
    SubmitBody,
    TaskConfigBody,
)

REMOTE_SHIM_PORT = 10998
REMOTE_RUNNER_PORT = 10999
REQUEST_TIMEOUT = 15


@dataclass
class HealthStatus:
    healthy: bool
    reason: str

    def __str__(self) -> str:
        return self.reason


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
            resp = requests.get(self._url("/api/healthcheck"), timeout=REQUEST_TIMEOUT)
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
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

    def upload_code(self, file: Union[BinaryIO, bytes]):
        resp = requests.post(self._url("/api/upload_code"), data=file, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

    def run_job(self):
        resp = requests.post(self._url("/api/run"), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

    def pull(self, timestamp: int) -> PullResponse:
        resp = requests.get(
            self._url("/api/pull"), params={"timestamp": timestamp}, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        return PullResponse.__response__.parse_obj(resp.json())

    def stop(self):
        resp = requests.post(self._url("/api/stop"), timeout=REQUEST_TIMEOUT)
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
            resp = requests.get(self._url("/api/healthcheck"), timeout=REQUEST_TIMEOUT)
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
        public_keys: List[str],
        ssh_user: str,
        ssh_key: str,
        mounts: List[VolumeMountPoint],
        volumes: List[Volume],
    ):
        _shm_size = int(shm_size * 1024 * 1024 * 1014) if shm_size else 0
        volume_infos = [_volume_to_shim_volume_info(v) for v in volumes]
        post_body = TaskConfigBody(
            username=username,
            password=password,
            image_name=image_name,
            container_name=container_name,
            shm_size=_shm_size,
            public_keys=public_keys,
            ssh_user=ssh_user,
            ssh_key=ssh_key,
            mounts=mounts,
            volumes=volume_infos,
        ).dict()
        resp = requests.post(
            self._url("/api/submit"),
            json=post_body,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

    def stop(self, force: bool = False):
        body = StopBody(force=force)
        resp = requests.post(self._url("/api/stop"), json=body.dict(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

    def pull(self) -> PullBody:
        resp = requests.get(self._url("/api/pull"), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return PullBody.__response__.parse_obj(resp.json())

    def _url(self, path: str) -> str:
        return f"{'https' if self.secure else 'http'}://{self.hostname}:{self.port}/{path.lstrip('/')}"


def health_response_to_health_status(data: HealthcheckResponse) -> HealthStatus:
    if data.service == "dstack-shim":
        return HealthStatus(healthy=True, reason="Service is OK")
    else:
        return HealthStatus(
            healthy=False,
            reason=f"Service name is {data.service}, service version: {data.version}",
        )


def _volume_to_shim_volume_info(volume: Volume) -> ShimVolumeInfo:
    return ShimVolumeInfo(
        name=volume.name,
        volume_id=volume.volume_id,
        init_fs=not volume.external,
    )
