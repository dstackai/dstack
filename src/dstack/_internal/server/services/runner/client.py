import uuid
from dataclasses import dataclass
from http import HTTPStatus
from typing import BinaryIO, Dict, List, Optional, TypeVar, Union

import packaging.version
import requests
import requests.exceptions

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.common import CoreModel, NetworkMode
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.runs import ClusterInfo, JobSpec, RunSpec
from dstack._internal.core.models.volumes import InstanceMountPoint, Volume, VolumeMountPoint
from dstack._internal.server.schemas.runner import (
    GPUDevice,
    HealthcheckResponse,
    LegacyPullResponse,
    LegacyStopBody,
    LegacySubmitBody,
    MetricsResponse,
    PullResponse,
    ShimVolumeInfo,
    SubmitBody,
    TaskInfoResponse,
    TaskSubmitRequest,
    TaskTerminateRequest,
)
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

REQUEST_TIMEOUT = 9

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


class ShimError(DstackError):
    pass


class ShimHTTPError(DstackError):
    """
    An HTTP error wrapper for `requests.exceptions.HTTPError`. Should be used as follows:

        try:
            <do something>
        except requests.exceptions.HTTPError as e:
            raise ShimHTTPError() from e
    """

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.status_code})"

    @property
    def status_code(self) -> int:
        cause = self._cause
        if cause is not None and cause.response is not None:
            return cause.response.status_code
        return 0

    @property
    def message(self) -> str:
        cause = self._cause
        if cause is None:
            return "unknown_error"
        return str(cause)

    @property
    def _cause(self) -> Optional[requests.exceptions.HTTPError]:
        cause = self.__cause__
        if isinstance(cause, requests.exceptions.HTTPError):
            return cause
        return None


class ShimAPIVersionError(ShimError):
    pass


class ShimClient:
    # API v2 (a.k.a. Future API) — `/api/tasks/[:id[/{terminate,remove}]]`
    # API v1 (a.k.a. Legacy API) — `/api/{submit,pull,stop}`
    _API_V2_MIN_SHIM_VERSION = (0, 18, 34)

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

    # Methods shared by all API versions

    def is_api_v2_supported(self) -> bool:
        if not self._negotiated:
            self._negotiate()
        return self._api_version == 2

    def healthcheck(self, unmask_exeptions: bool = False) -> Optional[HealthcheckResponse]:
        try:
            resp = self._request("GET", "/api/healthcheck", raise_for_status=True)
        except requests.exceptions.RequestException:
            if unmask_exeptions:
                raise
            return None
        if not self._negotiated:
            self._negotiate(resp)
        return self._response(HealthcheckResponse, resp)

    # API v2 methods

    def get_task(self, task_id: "_TaskID") -> TaskInfoResponse:
        if not self.is_api_v2_supported():
            raise ShimAPIVersionError()
        resp = self._request("GET", f"/api/tasks/{task_id}", raise_for_status=True)
        return self._response(TaskInfoResponse, resp)

    def submit_task(
        self,
        task_id: "_TaskID",
        name: str,
        registry_username: str,
        registry_password: str,
        image_name: str,
        container_user: str,
        privileged: bool,
        gpu: Optional[int],
        cpu: Optional[float],
        memory: Optional[Memory],
        shm_size: Optional[Memory],
        network_mode: NetworkMode,
        volumes: list[Volume],
        volume_mounts: list[VolumeMountPoint],
        instance_mounts: list[InstanceMountPoint],
        gpu_devices: list[GPUDevice],
        host_ssh_user: str,
        host_ssh_keys: list[str],
        container_ssh_keys: list[str],
        instance_id: str,
    ) -> None:
        if not self.is_api_v2_supported():
            raise ShimAPIVersionError()
        body = TaskSubmitRequest(
            id=str(task_id),
            name=name,
            registry_username=registry_username,
            registry_password=registry_password,
            image_name=image_name,
            container_user=container_user,
            privileged=privileged,
            gpu=gpu if gpu is not None else -1,  # None = -1 = "all available" (0 means "0 GPU")
            cpu=cpu if cpu is not None else 0,  # None = 0 = "all available"
            memory=_memory_to_bytes(memory),  # None = 0 = "all available"
            shm_size=_memory_to_bytes(shm_size),  # None = 0 = "use default value"
            network_mode=network_mode,
            volumes=[_volume_to_shim_volume_info(v, instance_id) for v in volumes],
            volume_mounts=volume_mounts,
            instance_mounts=instance_mounts,
            gpu_devices=gpu_devices,
            host_ssh_user=host_ssh_user,
            host_ssh_keys=host_ssh_keys,
            container_ssh_keys=container_ssh_keys,
        )
        self._request("POST", "/api/tasks", body, raise_for_status=True)

    def terminate_task(
        self,
        task_id: "_TaskID",
        reason: Optional[str] = None,
        message: Optional[str] = None,
        *,
        timeout: int = 10,
    ) -> None:
        if not self.is_api_v2_supported():
            raise ShimAPIVersionError()
        body = TaskTerminateRequest(
            termination_reason=reason or "",
            termination_message=message or "",
            timeout=timeout,
        )
        self._request("POST", f"/api/tasks/{task_id}/terminate", body, raise_for_status=True)

    def remove_task(self, task_id: "_TaskID") -> None:
        if not self.is_api_v2_supported():
            raise ShimAPIVersionError()
        self._request("POST", f"/api/tasks/{task_id}/remove", raise_for_status=True)

    # API v1 methods

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
        instance_id: str,
    ) -> bool:
        """
        Returns `True` if submitted and `False` if the shim already has a job (`409 Conflict`).
        Other error statuses raise an exception.
        """
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
            volumes=[_volume_to_shim_volume_info(v, instance_id) for v in volumes],
            instance_mounts=instance_mounts,
        )
        resp = self._request("POST", "/api/submit", body)
        if resp.status_code == HTTPStatus.CONFLICT:
            return False
        self._raise_for_status(resp)
        return True

    def stop(self, force: bool = False) -> None:
        body = LegacyStopBody(force=force)
        self._request("POST", "/api/stop", body, raise_for_status=True)

    def pull(self) -> LegacyPullResponse:
        resp = self._request("GET", "/api/pull", raise_for_status=True)
        return self._response(LegacyPullResponse, resp)

    # Metrics

    def get_task_metrics(self, task_id: "_TaskID") -> Optional[str]:
        resp = self._request("GET", f"/metrics/tasks/{task_id}")
        if resp.status_code == HTTPStatus.NOT_FOUND:
            # Metrics exporter is not installed or old shim version
            return None
        if resp.status_code == HTTPStatus.BAD_GATEWAY:
            # Metrics exporter is not available or returned an error
            logger.info("failed to collect metrics for task %s: %s", task_id, resp.text)
            return None
        self._raise_for_status(resp)
        return resp.text

    # Private methods used for public methods implementations

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
            self._raise_for_status(resp)
        return resp

    _M = TypeVar("_M", bound=CoreModel)

    def _response(self, model_cls: type[_M], response: requests.Response) -> _M:
        return model_cls.__response__.parse_obj(response.json())

    def _raise_for_status(self, response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise ShimHTTPError() from e

    def _negotiate(self, healthcheck_response: Optional[requests.Response] = None) -> None:
        if healthcheck_response is None:
            healthcheck_response = self._request("GET", "/api/healthcheck", raise_for_status=True)
        raw_version = self._response(HealthcheckResponse, healthcheck_response).version
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


def _volume_to_shim_volume_info(volume: Volume, instance_id: str) -> ShimVolumeInfo:
    device_name = None
    attachment_data = volume.get_attachment_data_for_instance(instance_id)
    if attachment_data is not None:
        device_name = attachment_data.device_name
    return ShimVolumeInfo(
        backend=volume.configuration.backend.value,
        name=volume.name,
        volume_id=get_or_error(volume.volume_id),
        init_fs=not volume.external,
        device_name=device_name,
    )


def _memory_to_bytes(memory: Optional[Memory]) -> int:
    if memory is None:
        return 0
    return int(memory * 1024**3)


_TaskID = Union[uuid.UUID, str]

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
