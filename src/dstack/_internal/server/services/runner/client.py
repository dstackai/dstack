from dataclasses import dataclass
from http import HTTPStatus
from typing import BinaryIO, Dict, List, Optional, TypeVar, Union

import packaging.version
import requests
import requests.exceptions

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import ClusterInfo, JobSpec, RunSpec
from dstack._internal.core.models.volumes import InstanceMountPoint, Volume, VolumeMountPoint
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    JobResult,
    LegacyPullResponse,
    LegacyStopBody,
    LegacySubmitBody,
    MetricsResponse,
    PullResponse,
    ShimVolumeInfo,
    SubmitBody,
    TaskInfoResponse,
    TaskStatus,
    TaskSubmitRequest,
    TaskTerminateRequest,
)
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

REMOTE_SHIM_PORT = 10998
REMOTE_RUNNER_PORT = 10999
REQUEST_TIMEOUT = 15

logger = get_logger(__name__)


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

    def get_metrics(self) -> Optional[MetricsResponse]:
        resp = requests.get(self._url("/api/metrics"), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return MetricsResponse.__response__.parse_obj(resp.json())

    def submit_job(
        self,
        run_spec: RunSpec,
        job_spec: JobSpec,
        cluster_info: ClusterInfo,
        secrets: Dict[str, str],
        repo_credentials: Optional[RemoteRepoCreds],
        instance_env: Optional[Union[Env, Dict[str, str]]] = None,
    ):
        # XXX: This is a quick-and-dirty hack to deliver InstanceModel-specific environment
        # variables to the runner without runner API modification.
        if instance_env is not None:
            if isinstance(instance_env, Env):
                merged_env = instance_env.as_dict()
            else:
                merged_env = instance_env.copy()
            merged_env.update(job_spec.env)
            job_spec = job_spec.copy(deep=True)
            job_spec.env = merged_env
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
    # API v2 (a.k.a. Future API) — `/api/tasks/[:id[/{terminate,remove}]]`
    # API v1 (a.k.a. Legacy API) — `/api/{submit,pull,stop}`
    _API_V2_MIN_SHIM_VERSION = (0, 18, 34)

    # A surrogate task ID for API-v1-over-v2 emulation (`_v2_compat_*` methods)
    _LEGACY_TASK_ID = "00000000-0000-0000-0000-000000000000"

    _shim_version: Optional["_Version"]
    _api_version: int
    _negotiated: bool = False

    def __init__(
        self,
        port: int,
        hostname: str = "localhost",
    ):
        self._session = requests.Session()
        self._base_url = f"http://{hostname}:{port}"

    def healthcheck(self, unmask_exeptions: bool = False) -> Optional[HealthcheckResponse]:
        try:
            resp = self._request("GET", "/api/healthcheck", raise_for_status=True)
        except requests.exceptions.RequestException:
            if unmask_exeptions:
                raise
            return None
        return self._response(HealthcheckResponse, resp)

    def submit(
        self,
        username: str,
        password: str,
        image_name: str,
        privileged: bool,
        container_name: str,
        container_user: str,
        shm_size: Optional[Memory],
        public_keys: List[str],
        ssh_user: str,
        ssh_key: str,
        mounts: List[VolumeMountPoint],
        volumes: List[Volume],
        instance_mounts: List[InstanceMountPoint],
    ) -> bool:
        """
        Returns `True` if submitted and `False` if the shim already has a job (`409 Conflict`).
        Other error statuses raise an exception.
        """
        if self._is_api_v2_supported():
            return self._v2_compat_submit(
                username=username,
                password=password,
                image_name=image_name,
                privileged=privileged,
                container_name=container_name,
                container_user=container_user,
                shm_size=shm_size,
                public_keys=public_keys,
                ssh_user=ssh_user,
                ssh_key=ssh_key,
                mounts=mounts,
                volumes=volumes,
                instance_mounts=instance_mounts,
            )
        body = LegacySubmitBody(
            username=username,
            password=password,
            image_name=image_name,
            privileged=privileged,
            container_name=container_name,
            container_user=container_user,
            shm_size=int(shm_size * 1024**3) if shm_size else 0,
            public_keys=public_keys,
            ssh_user=ssh_user,
            ssh_key=ssh_key,
            mounts=mounts,
            volumes=[_volume_to_shim_volume_info(v) for v in volumes],
            instance_mounts=instance_mounts,
        )
        resp = self._request("POST", "/api/submit", body)
        if resp.status_code == HTTPStatus.CONFLICT:
            return False
        resp.raise_for_status()
        return True

    def stop(self, force: bool = False) -> None:
        if self._is_api_v2_supported():
            return self._v2_compat_stop(force)
        body = LegacyStopBody(force=force)
        self._request("POST", "/api/stop", body, raise_for_status=True)

    def pull(self) -> LegacyPullResponse:
        if self._is_api_v2_supported():
            return self._v2_compat_pull()
        resp = self._request("GET", "/api/pull", raise_for_status=True)
        return self._response(LegacyPullResponse, resp)

    def _v2_compat_submit(
        self,
        username: str,
        password: str,
        image_name: str,
        privileged: bool,
        container_name: str,
        container_user: str,
        shm_size: Optional[Memory],
        public_keys: list[str],
        ssh_user: str,
        ssh_key: str,
        mounts: list[VolumeMountPoint],
        volumes: list[Volume],
        instance_mounts: List[InstanceMountPoint],
    ) -> bool:
        task_id = self._LEGACY_TASK_ID
        resp = self._request("GET", f"/api/tasks/{task_id}")
        if resp.status_code != HTTPStatus.NOT_FOUND:
            resp.raise_for_status()
            task = self._response(TaskInfoResponse, resp)
            if task.status != TaskStatus.TERMINATED:
                return False
            self._request("POST", f"/api/tasks/{task_id}/remove", raise_for_status=True)
        body = TaskSubmitRequest(
            id=task_id,
            name=container_name,
            registry_username=username,
            registry_password=password,
            image_name=image_name,
            container_user=container_user,
            privileged=privileged,
            gpu=-1,
            cpu=0,
            memory=0,
            shm_size=int(shm_size * 1024**3) if shm_size else 0,
            volumes=[_volume_to_shim_volume_info(v) for v in volumes],
            volume_mounts=mounts,
            instance_mounts=instance_mounts,
            host_ssh_user=ssh_user,
            host_ssh_keys=[ssh_key],
            container_ssh_keys=public_keys,
        )
        resp = self._request("POST", "/api/tasks", body, raise_for_status=True)
        return True

    def _v2_compat_stop(self, force: bool = False) -> None:
        task_id = self._LEGACY_TASK_ID
        body = TaskTerminateRequest(
            termination_reason="",
            termination_message="",
            timeout=0 if force else 10,
        )
        resp = self._request("POST", f"/api/tasks/{task_id}/terminate", body)
        if resp.status_code == HTTPStatus.NOT_FOUND:
            return
        resp.raise_for_status()

    def _v2_compat_pull(self) -> LegacyPullResponse:
        task_id = self._LEGACY_TASK_ID
        resp = self._request("GET", f"/api/tasks/{task_id}")
        if resp.status_code == HTTPStatus.NOT_FOUND:
            return LegacyPullResponse(
                state="pending",
                result=JobResult(reason="", reason_message=""),
            )
        resp.raise_for_status()
        task = self._response(TaskInfoResponse, resp)
        if task.status in [TaskStatus.PENDING, TaskStatus.PREPARING, TaskStatus.PULLING]:
            state = "pulling"
        elif task.status == TaskStatus.CREATING:
            state = "creating"
        elif task.status == TaskStatus.RUNNING:
            state = "running"
        elif task.status == TaskStatus.TERMINATED:
            state = "pending"
        else:
            assert False, f"should not reach here: {task.status}"
        return LegacyPullResponse(
            state=state,
            result=JobResult(
                reason=task.termination_reason, reason_message=task.termination_message
            ),
        )

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[CoreModel] = None,
        *,
        raise_for_status: bool = False,
    ) -> requests.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"
        if body is not None:
            json = body.dict()
        else:
            json = None
        resp = self._session.request(method, url, json=json, timeout=REQUEST_TIMEOUT)
        if raise_for_status:
            resp.raise_for_status()
        return resp

    _M = TypeVar("_M", bound=CoreModel)

    def _response(self, model_cls: type[_M], response: requests.Response) -> _M:
        return model_cls.__response__.parse_obj(response.json())

    def _is_api_v2_supported(self) -> bool:
        if not self._negotiated:
            self._negotiate()
        return self._api_version >= 2

    def _negotiate(self) -> None:
        resp = self._request("GET", "/api/healthcheck", raise_for_status=True)
        raw_version = self._response(HealthcheckResponse, resp).version
        version = _parse_version(raw_version)
        if version is None or version >= self._API_V2_MIN_SHIM_VERSION:
            api_version = 2
        else:
            api_version = 1
        logger.debug(
            "shim version: %s %s (API v%s)",
            raw_version,
            version or "(latest)",
            api_version,
        )
        self._shim_version = version
        self._api_version = api_version
        self._negotiated = True


def health_response_to_health_status(data: HealthcheckResponse) -> HealthStatus:
    if data.service == "dstack-shim":
        return HealthStatus(healthy=True, reason="Service is OK")
    else:
        return HealthStatus(
            healthy=False,
            reason=f"Service name is {data.service}, service version: {data.version}",
        )


def _volume_to_shim_volume_info(volume: Volume) -> ShimVolumeInfo:
    device_name = None
    if volume.attachment_data is not None:
        device_name = volume.attachment_data.device_name
    return ShimVolumeInfo(
        backend=volume.configuration.backend.value,
        name=volume.name,
        volume_id=get_or_error(volume.volume_id),
        init_fs=not volume.external,
        device_name=device_name,
    )


_Version = tuple[int, int, int]


def _parse_version(version_string: str) -> Optional[_Version]:
    """
    Returns a (major, minor, micro) tuple if the version if final.
    Returns `None`, which means "latest", if:
    * the version is prerelease or dev build -- assuming that in most cases it's a build based on
    the latest final release
    * the version consists of only major part or not valid at all, e.g., staging builds have
    GitHub run number (e.g., 1234) instead of the version -- assuming that it's a "bleeding edge",
    not yet released version
    """
    try:
        version = packaging.version.parse(version_string)
    except packaging.version.InvalidVersion:
        return None
    if version.is_prerelease or version.is_devrelease:
        return None
    release = version.release
    if len(release) <= 1:
        return None
    if len(release) == 2:
        return (*release, 0)
    return release[:3]
