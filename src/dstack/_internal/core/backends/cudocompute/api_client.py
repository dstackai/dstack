from typing import Any, Dict, List

import requests

from dstack._internal.utils.ssh import get_public_key_fingerprint

API_URL = "https://rest.compute.cudo.org/v1"


class CudoComputeApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def create_virtual_machine(
        self,
        project_id: str,
        boot_disk_storage_class: str,
        boot_disk_size_gib: int,
        book_disk_id: str,
        boot_disk_image_id: str,
        data_center_id: str,
        gpu_model: str,
        gpus: int,
        machine_type: str,
        memory_gib: int,
        password: str,
        vcpus: int,
        vm_id: str,
        customSshKeys,
        start_script: str = None,
    ):
        data = {
            "bootDisk": {
                "storage_class": boot_disk_storage_class,
                "size_gib": boot_disk_size_gib,
                "id": book_disk_id,
            },
            "bootDiskImageId": boot_disk_image_id,
            "dataCenterId": data_center_id,
            "gpuModel": gpu_model,
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
        if resp.ok:
            data = resp.json()
            return data
        resp.raise_for_status()

    def terminate_virtual_machine(self, vm_id: str, project_id):
        resp = self._make_request("POST", f"/projects/{project_id}/vms/dstack-vm-id/terminate")
        if resp.ok:
            data = resp.json()
            return data
        resp.raise_for_status()

    def _make_request(self, method: str, path: str, data: Any = None):
        return requests.request(
            method=method,
            url=API_URL + path,
            json=data,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def get_or_create_ssh_key(self, public_key: str) -> str:
        fingerprint = get_public_key_fingerprint(public_key)
        keys = self.list_ssh_keys()
        found_keys = [key for key in keys if fingerprint == key["fingerprint"]]
        print(found_keys)
        if found_keys:
            key = found_keys[0]
            return key["id"]

        key_id = self.create_ssh_key(public_key)
        return key_id

    def list_ssh_keys(self) -> List[Dict]:
        resp = self._make_request("GET", "/ssh-keys")
        if resp.ok:
            return resp.json()["sshKeys"]
        resp.raise_for_status()

    def create_ssh_key(self, public_key: str) -> List[Dict]:
        data = {"publicKey": public_key}
        resp = self._make_request("POST", "/ssh-keys", data)
        if resp.ok:
            return resp.json()["id"]
        resp.raise_for_status()

    def get_vm(self, project_id, vm_id):
        resp = self._make_request("GET", f"/projects/{project_id}/vms/{vm_id}")
        if resp.ok:
            return resp.json()
        resp.raise_for_status()
