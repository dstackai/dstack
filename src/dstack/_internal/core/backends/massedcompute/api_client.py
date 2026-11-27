from typing import Optional, TypeVar, Union
from urllib.parse import quote
from uuid import UUID

import requests
from pydantic import AwareDatetime, Field, ValidationError
from typing_extensions import TypedDict

from dstack._internal.core.errors import BackendAuthError, ComputeError
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


class _TerminateRequest(TypedDict, closed=True):
    instanceUuids: list[str]


class MassedComputeAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self._request("POST", "/account/token/validation")
        except BackendAuthError:
            return False
        return True

    def launch(self, name: str, product: str, command: str) -> str:
        """Launch once using a unique name. If the response is lost, look up that name.

        Return the VM ID only when creation is confirmed. If the VM is not yet visible,
        propagate the launch error. Its name still lets orphan cleanup find it later.
        """
        payload: _LaunchRequest = {
            "instanceName": name,
            "productName": product,
            "imageId": 84,  # Ubuntu Server 22.04 w/ drivers
            "regionName": "any",
            "sshKeys": [],
            "command": command,
        }
        try:
            response = self._request("POST", "/instance/launch", payload)
            return str(_parse_response(_LaunchResponse, response).response)
        except ComputeError:
            matches = [vm.uuid for vm in self.list_instances() if vm.name == name]
            if len(matches) != 1:
                raise
            return matches[0]

    def list_instances(self) -> list[MassedComputeInstance]:
        return _parse_response(_Instances, self._request("GET", "/instance")).instances

    def get_instance(self, instance_id: str) -> Optional[MassedComputeInstance]:
        response = self._request("GET", "/instance/" + quote(instance_id, safe=""))
        # The detail endpoint returns the same array as the list endpoint, empty after deletion.
        instances = _parse_response(_Instances, response).instances
        if not instances:
            return None
        if len(instances) != 1 or instances[0].uuid != instance_id:
            raise ComputeError("MassedCompute returned an unexpected instance ID")
        return instances[0]

    def terminate(self, instance_id: str) -> None:
        self._request("POST", "/instance/terminate", {"instanceUuids": [instance_id]})

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Union[_LaunchRequest, _TerminateRequest]] = None,
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
            raise ComputeError(f"MassedCompute {method} {path}: {type(e).__name__}") from None
        if response.status_code == 401:
            raise BackendAuthError("Invalid MassedCompute API key")
        if not 200 <= response.status_code < 300:
            raise ComputeError(f"MassedCompute {method} {path}: HTTP {response.status_code}")
        return response


def _parse_response(model: type[_T], response: requests.Response) -> _T:
    try:
        return validate_json_extra_ignore(model, response.content)
    except ValidationError:
        # Instance payloads contain plaintext passwords, including in Pydantic's error inputs.
        raise ComputeError("Unexpected response from MassedCompute") from None
