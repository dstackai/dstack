from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, List, Literal, NotRequired, Optional, TypedDict, cast

import requests
from gpuhunt.providers.runpod import RunpodProvider

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

API_V2_URL = "https://api.runpod.io/v2"

REQUEST_TIMEOUT = 120

AUTH_ERROR_STATUS_CODES = (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)

PAGINATION_PAGE_LIMIT = 1000
"""The maximum page size of paginated v2 endpoints."""

PAGINATION_MAX_PAGES = 20

# Applies to non-JSON error responses, which are not expected to contain anything useful past
# the first few lines
MAX_ERROR_DETAIL_LEN = 200


class V2ErrorResponse(TypedDict):
    title: str
    status: int
    detail: str
    errors: NotRequired[list[str]]


V2Cloud = Literal["SECURE", "COMMUNITY"]
"""Cloud tier.
`SECURE` — Runpod-owned datacenter hardware, `COMMUNITY` — community-hosted hardware"""


class V2Pod(TypedDict):
    id: str
    name: str
    status: Literal["PROVISIONING", "STARTING", "RUNNING", "EXITED", "ERROR", "TERMINATED"]
    runtime: Optional["V2PodRuntime"]
    mounts: "V2Mounts"
    createdAt: str
    dataCenterId: Optional[str]


class V2Pagination(TypedDict):
    nextCursor: Optional[str]
    hasNextPage: bool


class V2PodRuntime(TypedDict):
    ports: NotRequired[list["V2PodRuntimePort"]]


class V2PodRuntimePort(TypedDict):
    private: NotRequired[int]
    public: NotRequired[Optional[int]]
    ip: NotRequired[Optional[str]]


class V2Mounts(TypedDict):
    network: NotRequired[list["V2NetworkMount"]]
    """The `network` field is an array for forward compatibility with eventual multi-network-volume
    support, but `maxItems` is 1 today"""


class V2NetworkMount(TypedDict):
    volumeId: str
    path: str


class V2CreatePodRequest(TypedDict):
    """
    Request body for creating a pod. Exactly one of `gpu` or `cpu` must be set.
    """

    name: str
    cloud: NotRequired[V2Cloud]
    """Cloud tier. Defaults to `SECURE` when omitted"""
    dataCenterIds: NotRequired[list[str]]
    """Preferred data centers for placement. Omit or pass an empty array to let
    the scheduler choose."""
    gpu: NotRequired["V2CreateGpuConfig"]
    cpu: NotRequired["V2CreateCpuConfig"]
    templateId: NotRequired[str]
    """ID of a pod template to base this pod on. The template is resolved at create time into
    the same container settings you could otherwise spread into this body."""
    disk: NotRequired[int]
    """Container disk in GB (ephemeral, wiped on restart)"""
    mounts: NotRequired["V2Mounts"]
    image: NotRequired[str]
    """`image` is required unless `templateId` is set"""
    registry: NotRequired[Optional[str]]
    """Container registry credential ID (for private images)"""
    entrypoint: NotRequired[list[str]]
    """Container ENTRYPOINT in exec form"""
    cmd: NotRequired[list[str]]
    """Container CMD in exec form"""
    ports: NotRequired[list[str]]
    """Exposed ports, formatted as port/protocol"""
    env: NotRequired[dict[str, str]]


class V2UpdatePodRequest(TypedDict):
    registry: NotRequired[Optional[str]]


class V2CreateGpuConfig(TypedDict):
    id: str
    """GPU type identifier, as returned by `GET /v2/catalog/gpus`"""
    count: NotRequired[int]
    """Number of GPUs. Default: `1`"""
    minCudaVersion: NotRequired[str]
    """Lowest acceptable CUDA version for the host machine, as `major.minor`"""
    minRamPerGpu: NotRequired[int]
    """Minimum host system RAM in GB per requested GPU. This is a placement filter, not a resource
    request. The actual total allocated system RAM may be higher and is returned in `gpu.memory`"""
    minVcpuCountPerGpu: NotRequired[int]
    """Minimum host vCPU count per requested GPU. This is a placement filter, not a resource
    request. The actual total allocated vCPU count may be higher and is returned in `gpu.vcpuCount`
    """


class V2CreateCpuConfig(TypedDict):
    id: str
    """CPU flavor identifier, as returned by `GET /v2/catalog/cpus`"""
    vcpuCount: int
    """Number of vCPUs. Must be valid for the selected CPU flavor and must be a power of two."""


class V2Registry(TypedDict):
    id: str
    name: str


class V2CreateRegistryRequest(TypedDict):
    name: str
    password: str
    username: str


class V2ListRegistriesResponse(TypedDict):
    registries: list[V2Registry]


V2VolumeType = Literal["STANDARD", "HIGH_PERFORMANCE"]


class V2NetworkVolume(TypedDict):
    id: str
    name: str
    """Human-readable name (not required to be unique)"""
    size: int
    """Allocated storage in GB, [ 10 .. 4096 ]"""
    dataCenter: str
    type: V2VolumeType


class V2CreateNetworkVolumeRequest(TypedDict):
    name: str
    size: int
    """Storage to allocate in GB, [ 10 .. 4096 ]"""
    dataCenter: str
    type: NotRequired[V2VolumeType]
    """ When omitted, the volume is provisioned using the requested data center's default (primary)
    storage tier."""


class RunpodV2ClientError(BackendError):
    def __init__(
        self, *, status: int, title: str, detail: str, errors: Optional[list[str]] = None
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors or []

    def __str__(self) -> str:
        parts: list[str] = [str(self.status), self.title, self.detail.rstrip(".")]
        # NOTE: Exceptions are exposed to the end user. We assume `errors` doesn't contain
        # sensitive data
        if self.errors:
            parts.append(repr(self.errors))
        return ": ".join(parts)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self})"


class RunpodApiClient:
    def __init__(self, api_key: str):
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {api_key}"})

    def validate_api_key(self) -> bool:
        try:
            self._make_v2_request("GET", "account", "ssh-keys")
        except BackendInvalidCredentialsError:
            return False
        return True

    def create_pod(
        self,
        *,
        name: str,
        cloud: V2Cloud,
        data_center_ids: Optional[list[str]] = None,
        gpu_type_id: Optional[str] = None,
        gpu_count: Optional[int] = None,
        min_cpu_count_per_gpu: Optional[int] = None,
        min_memory_in_gb_per_gpu: Optional[int] = None,
        cpu_type_id: Optional[str] = None,
        cpu_count: Optional[int] = None,
        container_disk_in_gb: int,
        network_volume_id: Optional[str] = None,
        volume_mount_path: Optional[str] = None,
        image_name: str,
        container_registry_credentials_id: Optional[str] = None,
        entrypoint: list[str],
        cmd: list[str],
        ports: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
    ) -> V2Pod:
        body: V2CreatePodRequest = {
            "name": name,
            "cloud": cloud,
            "image": image_name,
            "entrypoint": entrypoint,
            "cmd": cmd,
            "disk": container_disk_in_gb,
        }

        if (gpu_type_id is None) == (cpu_type_id is None):
            raise ValueError("Exactly one of CPU or GPU type must be set")
        if gpu_type_id is not None:
            if cpu_count is not None:
                raise ValueError("cpu_count is not applicable for GPU pods")
            gpu_config: V2CreateGpuConfig = {
                "id": gpu_type_id,
                "minCudaVersion": RunpodProvider.MIN_CUDA_VERSION,
            }
            if gpu_count is not None:
                gpu_config["count"] = gpu_count
            if min_cpu_count_per_gpu is not None:
                gpu_config["minVcpuCountPerGpu"] = min_cpu_count_per_gpu
            if min_memory_in_gb_per_gpu is not None:
                gpu_config["minRamPerGpu"] = min_memory_in_gb_per_gpu
            body["gpu"] = gpu_config
        else:
            if cpu_count is None:
                raise ValueError("cpu_count is required for CPU pods")
            assert cpu_type_id is not None
            cpu_config: V2CreateCpuConfig = {
                "id": cpu_type_id,
                "vcpuCount": cpu_count,
            }
            body["cpu"] = cpu_config

        mounts = _build_v2_mounts(network_volume_id, volume_mount_path)
        if mounts is not None:
            body["mounts"] = mounts

        if data_center_ids is not None:
            body["dataCenterIds"] = data_center_ids
        if container_registry_credentials_id is not None:
            body["registry"] = container_registry_credentials_id
        if ports is not None:
            body["ports"] = ports
        if env is not None:
            body["env"] = env

        response = self._make_v2_request("POST", "pods", json=body)
        return response.json()

    def get_pod(self, pod_id: str) -> Optional[V2Pod]:
        try:
            response = self._make_v2_request("GET", "pods", pod_id)
        except RunpodV2ClientError as e:
            if e.status == HTTPStatus.NOT_FOUND:
                return None
            raise
        return response.json()

    def list_pods(self) -> list[V2Pod]:
        """
        Lists pods. Deleted pods are not listed.
        """
        return self._paginate_v2("pods", response_key="pods")

    def terminate_pod(self, pod_id: str) -> bool:
        try:
            self._make_v2_request("DELETE", "pods", pod_id)
        except RunpodV2ClientError as e:
            if e.status == HTTPStatus.NOT_FOUND:
                return False
            raise
        return True

    def list_container_registry_credentials(self) -> List[V2Registry]:
        response = self._make_v2_request("GET", "registries")
        response_json: V2ListRegistriesResponse = response.json()
        return response_json["registries"]

    def create_container_registry_credentials(
        self,
        *,
        name: str,
        username: str,
        password: str,
    ) -> V2Registry:
        body: V2CreateRegistryRequest = {
            "name": name,
            "username": username,
            "password": password,
        }
        response = self._make_v2_request("POST", "registries", json=body)
        return response.json()

    def delete_container_registry_credentials(self, credentials_id: str) -> None:
        # As of 2026-09-18, v2 API returns 400 with "detail": "Registry auth not found"
        # instead of 404, hence we don't handle "not found" case
        self._make_v2_request("DELETE", "registries", credentials_id)

    def get_network_volume(self, volume_id: str) -> Optional[V2NetworkVolume]:
        try:
            response = self._make_v2_request("GET", "network-volumes", volume_id)
        except RunpodV2ClientError as e:
            if e.status == HTTPStatus.NOT_FOUND:
                return None
            raise
        return response.json()

    def create_network_volume(
        self, *, name: str, data_center_id: str, size: int
    ) -> V2NetworkVolume:
        body: V2CreateNetworkVolumeRequest = {
            "name": name,
            "dataCenter": data_center_id,
            "size": size,
        }
        response = self._make_v2_request("POST", "network-volumes", json=body)
        return response.json()

    def delete_network_volume(self, volume_id: str) -> bool:
        try:
            self._make_v2_request("DELETE", "network-volumes", volume_id)
        except RunpodV2ClientError as e:
            if e.status == HTTPStatus.NOT_FOUND:
                return False
            raise
        return True

    def _paginate_v2(self, *path_parts: str, response_key: str) -> list[Any]:
        """
        Follows `pagination.nextCursor` of a cursor-paginated GET endpoint and returns
        the items of all pages, or of the first `PAGINATION_MAX_PAGES` pages.
        """
        result = []
        params: dict[str, Any] = {"limit": PAGINATION_PAGE_LIMIT}
        for _ in range(PAGINATION_MAX_PAGES):
            response_json = self._make_v2_request("GET", *path_parts, params=params).json()
            result.extend(response_json[response_key])
            pagination: V2Pagination = response_json["pagination"]
            if not pagination["hasNextPage"] or pagination["nextCursor"] is None:
                break
            params["cursor"] = pagination["nextCursor"]
        else:
            logger.error(
                "Listing %s exceeded the limit of %s pages, the rest is skipped",
                "/".join(path_parts),
                PAGINATION_MAX_PAGES,
            )
        return result

    def _make_v2_request(
        self,
        method: str,
        /,
        *path_parts: str,
        json: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> requests.Response:
        url = "/".join((API_V2_URL, *path_parts))
        response = self._session.request(
            method=method,
            url=url,
            timeout=REQUEST_TIMEOUT,
            json=json,
            params=params,
        )
        if HTTPStatus.BAD_REQUEST <= response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR:
            error = _parse_v2_error_response(response)
            logger.debug("Runpod API v2 error: %s", error)
            if response.status_code in AUTH_ERROR_STATUS_CODES:
                raise BackendInvalidCredentialsError(f"{error['title']}: {error['detail']}")
            raise RunpodV2ClientError(
                status=response.status_code,
                title=error["title"],
                detail=error["detail"],
                errors=error.get("errors"),
            )
        response.raise_for_status()
        return response


def _parse_v2_error_response(response: requests.Response) -> V2ErrorResponse:
    try:
        error = response.json()
    except requests.JSONDecodeError:
        error = None
    if isinstance(error, dict) and "title" in error and "detail" in error:
        return cast(V2ErrorResponse, error)
    # Not a v2 error response, e.g., an HTML page served by a proxy in front of the API
    return {
        "title": response.reason or "Unknown error",
        "status": response.status_code,
        "detail": " ".join(response.text.split())[:MAX_ERROR_DETAIL_LEN],
    }


def _build_v2_mounts(
    network_volume_id: Optional[str], volume_mount_path: Optional[str]
) -> Optional[V2Mounts]:
    if network_volume_id is not None:
        if volume_mount_path is None:
            raise ValueError("volume_mount_path must be set if network_volume_id is set")
        network_mount: V2NetworkMount = {
            "volumeId": network_volume_id,
            "path": volume_mount_path,
        }
        mounts: V2Mounts = {"network": [network_mount]}
        return mounts
    elif volume_mount_path is not None:
        raise ValueError("volume_mount_path must not be set if network_volume_id is not set")
    return None
