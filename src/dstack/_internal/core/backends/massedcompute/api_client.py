from typing import Optional, TypeVar, Union
from urllib.parse import quote
from uuid import UUID

import requests
from pydantic import AwareDatetime, Field, ValidationError
from typing_extensions import NotRequired, TypedDict

from dstack._internal.core.errors import (
    BackendAuthError,
    ComputeError,
    VolumeDeletionPending,
    VolumeProvisioningError,
    VolumeProvisioningPending,
)
from dstack._internal.core.models.common import CoreModel, validate_json_extra_ignore

API_URL = "https://vm.massedcompute.com/api/v1"
_T = TypeVar("_T", bound=CoreModel)


class MassedComputeInstance(CoreModel):
    uuid: str
    name: str
    status: str
    ip: Optional[str] = None
    username: Optional[str] = None
    os_booted: bool = False
    created: Optional[AwareDatetime] = None

    def get_uuid(self) -> UUID:
        try:
            return UUID(self.uuid)
        except ValueError:
            raise ComputeError("MassedCompute returned an invalid VM UUID") from None


class _AttachedInstance(CoreModel):
    uuid: UUID


class _VolumeIdentity(CoreModel):
    id: UUID
    name: str


class MassedComputeVolume(_VolumeIdentity):
    status: str
    mount_path: str = Field(alias="mountPath")
    can_manage: bool = Field(alias="canManage")
    attached_to: list[_AttachedInstance] = Field(alias="attachedTo")
    hidden_attached_count: int = Field(alias="hiddenAttachedCount")


class _Volumes(CoreModel):
    volumes: list[MassedComputeVolume] = Field(alias="storageVolumes")


class _CreatedVolume(CoreModel):
    volume: _VolumeIdentity = Field(alias="storageVolume")


class _VolumeDeletion(CoreModel):
    id: Optional[UUID] = None
    deleted: bool


class _DeletedVolume(CoreModel):
    result: _VolumeDeletion


class _CreateVolumeRequest(TypedDict, closed=True):
    name: str


class _Instances(CoreModel):
    instances: list[MassedComputeInstance] = Field(alias="runningInstances")


class _LaunchResponse(CoreModel):
    response: UUID


class _LaunchRequest(TypedDict, closed=True):
    instanceName: str
    productName: str
    imageId: int
    regionName: str
    command: str
    sshKeys: list[str]
    volumeIds: NotRequired[list[str]]


class _TerminateRequest(TypedDict, closed=True):
    instanceUuids: list[str]


class MassedComputeLaunchUnconfirmed(ComputeError):
    """A volume VM may have been created. Reconcile its unique name before retrying."""


class _RequestRejected(ComputeError):
    """The request was never sent, or the API reported a documented rejection."""


class MassedComputeAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self._request("POST", "/account/token/validation")
        except BackendAuthError:
            return False
        return True

    def launch(
        self, name: str, product: str, command: str, volume_ids: Optional[list[str]] = None
    ) -> str:
        """Recover a lost VM launch response by name. Volume launches reconcile in the worker."""
        payload: _LaunchRequest = {
            "instanceName": name,
            "productName": product,
            "imageId": 84,  # Ubuntu Server 22.04 w/ drivers
            "regionName": "any",
            "sshKeys": [],
            "command": command,
        }
        if volume_ids:
            payload["volumeIds"] = volume_ids
        try:
            # With volumeIds, these are the documented storage permission, unknown ID,
            # inactive storage, and invalid request errors, respectively.
            response = self._request(
                "POST",
                "/instance/launch",
                payload,
                rejected_statuses=(403, 404, 409, 422) if volume_ids else (),
            )
            return str(_parse_response(_LaunchResponse, response).response)
        except _RequestRejected:
            raise
        except ComputeError as e:
            if volume_ids:
                raise MassedComputeLaunchUnconfirmed(str(e)) from e
            matches = [vm for vm in self.list_instances() if vm.name == name]
            if len(matches) != 1:
                raise
            return str(matches[0].get_uuid())

    def list_instances(self) -> list[MassedComputeInstance]:
        return _parse_response(_Instances, self._request("GET", "/instance")).instances

    def get_instance_by_name(self, name: str) -> Optional[MassedComputeInstance]:
        matches = [vm for vm in self.list_instances() if vm.name == name]
        if len(matches) > 1:
            raise ComputeError(f"Multiple MassedCompute instances match launch name {name}")
        return matches[0] if matches else None

    def get_instance(self, instance_id: str) -> Optional[MassedComputeInstance]:
        response = self._request("GET", "/instance/" + quote(instance_id, safe=""))
        # The detail endpoint returns the same array as the list endpoint, empty after deletion.
        instances = _parse_response(_Instances, response).instances
        if not instances:
            return None
        if len(instances) != 1 or instances[0].uuid.lower() != instance_id.lower():
            raise ComputeError("MassedCompute returned an unexpected instance ID")
        return instances[0]

    def terminate(self, instance_id: str) -> None:
        self._request("POST", "/instance/terminate", {"instanceUuids": [instance_id]})

    def list_volumes(self) -> list[MassedComputeVolume]:
        return _parse_response(_Volumes, self._request("GET", "/storage-volumes")).volumes

    def create_volume(self, name: str) -> str:
        payload: _CreateVolumeRequest = {"name": name}
        try:
            response = self._request(
                "POST",
                "/storage-volumes",
                payload,
                # Only the first worker may POST. A name conflict belongs to other storage.
                rejected_statuses=(403, 404, 409, 422),
            )
            volume = _parse_response(_CreatedVolume, response).volume
            if volume.name != name:
                raise ComputeError("MassedCompute returned an unexpected volume name")
            return str(volume.id)
        except (BackendAuthError, _RequestRejected) as e:
            raise VolumeProvisioningError(str(e), volume_id=None) from e
        except ComputeError as e:
            raise VolumeProvisioningPending(f"Unconfirmed creation of volume {name}: {e}") from e

    def delete_volume(self, volume_id: str) -> None:
        try:
            response = self._request(
                "DELETE", "/storage-volumes/" + quote(volume_id, safe=""), allowed_statuses=(404,)
            )
            # A repeated delete of a known UUID may already be absent from this account's view.
            if response.status_code == 404:
                return
            if response.status_code == 200:
                result = _parse_response(_DeletedVolume, response).result
                if result.id is not None and str(result.id) != volume_id.lower():
                    raise ComputeError("MassedCompute returned an unexpected deleted volume ID")
                if result.deleted:
                    return
        except (BackendAuthError, ComputeError) as e:
            raise VolumeDeletionPending(str(e)) from e
        raise VolumeDeletionPending("MassedCompute is still emptying the volume")

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Union[_LaunchRequest, _TerminateRequest, _CreateVolumeRequest]] = None,
        allowed_statuses: tuple[int, ...] = (),
        rejected_statuses: tuple[int, ...] = (),
    ) -> requests.Response:
        try:
            response = requests.request(
                method,
                API_URL + path,
                json=payload,
                timeout=30,
                allow_redirects=False,  # A redirect can replay a launch POST.
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except requests.RequestException as e:
            error = f"MassedCompute {method} {path}: {type(e).__name__}"
            if rejected_statuses and isinstance(e, requests.ConnectTimeout):
                raise _RequestRejected(error) from None
            raise ComputeError(error) from None
        if response.status_code == 401:
            raise BackendAuthError("Invalid MassedCompute API key")
        if not 200 <= response.status_code < 300 and response.status_code not in allowed_statuses:
            error = f"MassedCompute {method} {path}: HTTP {response.status_code}"
            if response.status_code in rejected_statuses:
                raise _RequestRejected(error)
            raise ComputeError(error)
        return response


def _parse_response(model: type[_T], response: requests.Response) -> _T:
    try:
        return validate_json_extra_ignore(model, response.content)
    except ValidationError:
        # Instance payloads contain plaintext passwords, including in Pydantic's error inputs.
        raise ComputeError("Unexpected response from MassedCompute") from None
