from typing import Any, Dict, List, Optional

import requests
from requests import Response

from dstack._internal.core.errors import BackendInvalidCredentialsError
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import get_public_key_fingerprint

API_URL = "https://rest.compute.cudo.org/v1"

logger = get_logger(__name__)


class CudoApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self.get_user_details()
        except BackendInvalidCredentialsError:
            return False
        return True

    def get_user_details(self) -> Dict:
        resp = self._make_request("GET", "/auth")
        return resp.json()

    def create_virtual_machine(
        self,
        project_id: str,
        boot_disk_storage_class: str,
        boot_disk_size_gib: int,
        book_disk_id: str,
        boot_disk_image_id: str,
        data_center_id: str,
        gpus: int,
        machine_type: str,
        memory_gib: int,
        password: Optional[str],
        vcpus: int,
        vm_id: str,
        customSshKeys,
        start_script: Optional[str] = None,
    ) -> Dict:
        data = {
            "bootDisk": {
                "storage_class": boot_disk_storage_class,
                "size_gib": boot_disk_size_gib,
                "id": book_disk_id,
            },
            "bootDiskImageId": boot_disk_image_id,
            "dataCenterId": data_center_id,
            "gpus": gpus,
            "machineType": machine_type,
            "memoryGib": memory_gib,
            "password": password,
            "vcpus": vcpus,
            "vmId": vm_id,
            "startScript": start_script,
            "customSshKeys": customSshKeys,
        }
        resp = self._make_request("POST", f"/projects/{project_id}/vm", data)
        return resp.json()

    def terminate_virtual_machine(self, vm_id: str, project_id: str) -> Dict:
        resp = self._make_request("POST", f"/projects/{project_id}/vms/{vm_id}/terminate")
        return resp.json()

    def _make_request(self, method: str, path: str, data: Any = None) -> Response:
        try:
            response = requests.request(
                method=method,
                url=API_URL + path,
                json=data,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            response.raise_for_status()
            return response
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (
                requests.codes.forbidden,
                requests.codes.unauthorized,
            ):
                raise BackendInvalidCredentialsError(e.response.text)
            raise

    def get_or_create_ssh_key(self, public_key: str) -> str:
        fingerprint = get_public_key_fingerprint(public_key)
        keys = self.list_ssh_keys()
        found_keys = [key for key in keys if fingerprint == key["fingerprint"]]
        if found_keys:
            key = found_keys[0]
            return key["id"]
        key_id = self.create_ssh_key(public_key)
        return key_id

    def list_ssh_keys(self) -> List[Dict]:
        resp = self._make_request("GET", "/ssh-keys")
        return resp.json()["sshKeys"]

    def create_ssh_key(self, public_key: str) -> str:
        data = {"publicKey": public_key}
        resp = self._make_request("POST", "/ssh-keys", data)
        return resp.json()["id"]

    def get_vm(self, project_id, vm_id) -> Dict:
        resp = self._make_request("GET", f"/projects/{project_id}/vms/{vm_id}")
        return resp.json()
