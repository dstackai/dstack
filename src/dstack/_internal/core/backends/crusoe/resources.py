import base64
import datetime
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional

import requests

from dstack._internal.core.backends.crusoe.models import CrusoeAccessKeyCreds
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://api.crusoecloud.com"
API_VERSION = "/v1alpha5"
SIGNATURE_VERSION = "1.0"
REQUEST_TIMEOUT = 30


class CrusoeClient:
    def __init__(self, creds: CrusoeAccessKeyCreds, project_id: str):
        self.access_key = creds.access_key
        self.secret_key = creds.secret_key
        self.project_id = project_id

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
    ) -> requests.Response:
        dt = str(datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0))
        dt = dt.replace(" ", "T")

        query_string = ""
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))

        payload = f"{API_VERSION}{path}\n{query_string}\n{method}\n{dt}\n"

        decoded_secret = base64.urlsafe_b64decode(
            self.secret_key + "=" * (-len(self.secret_key) % 4)
        )
        sig = hmac.new(decoded_secret, msg=payload.encode("ascii"), digestmod=hashlib.sha256)
        encoded_sig = base64.urlsafe_b64encode(sig.digest()).decode("ascii").rstrip("=")

        headers = {
            "X-Crusoe-Timestamp": dt,
            "Authorization": f"Bearer {SIGNATURE_VERSION}:{self.access_key}:{encoded_sig}",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        url = f"{API_URL}{API_VERSION}{path}"
        resp = requests.request(
            method, url, headers=headers, params=params, json=body, timeout=REQUEST_TIMEOUT
        )
        if resp.status_code >= 400:
            _raise_api_error(resp)
        return resp

    def _project_path(self, path: str) -> str:
        return f"/projects/{self.project_id}{path}"

    # --- VM operations ---

    def create_vm(
        self,
        name: str,
        vm_type: str,
        location: str,
        ssh_public_key: str,
        image: str,
        startup_script: str,
        disks: Optional[List[Dict[str, str]]] = None,
        host_channel_adapters: Optional[List[Dict[str, str]]] = None,
    ) -> dict:
        body: Dict[str, Any] = {
            "name": name,
            "type": vm_type,
            "location": location,
            "ssh_public_key": ssh_public_key,
            "image": image,
            "startup_script": startup_script,
        }
        if disks:
            body["disks"] = disks
        if host_channel_adapters:
            body["host_channel_adapters"] = host_channel_adapters
        resp = self._request("POST", self._project_path("/compute/vms/instances"), body=body)
        return resp.json()["operation"]

    def get_vm(self, vm_id: str) -> dict:
        resp = self._request("GET", self._project_path(f"/compute/vms/instances/{vm_id}"))
        return resp.json()

    def delete_vm(self, vm_id: str) -> dict:
        resp = self._request("DELETE", self._project_path(f"/compute/vms/instances/{vm_id}"))
        return resp.json()["operation"]

    def get_vm_operation(self, operation_id: str) -> dict:
        resp = self._request(
            "GET", self._project_path(f"/compute/vms/instances/operations/{operation_id}")
        )
        return resp.json()

    # --- Disk operations ---

    def create_disk(self, name: str, size: str, location: str) -> dict:
        body = {
            "name": name,
            "size": size,
            "location": location,
            "type": "persistent-ssd",
            "block_size": 4096,
        }
        resp = self._request("POST", self._project_path("/storage/disks"), body=body)
        return resp.json()["operation"]

    def delete_disk(self, disk_id: str) -> dict:
        resp = self._request("DELETE", self._project_path(f"/storage/disks/{disk_id}"))
        return resp.json()["operation"]

    def get_disk_operation(self, operation_id: str) -> dict:
        resp = self._request(
            "GET", self._project_path(f"/storage/disks/operations/{operation_id}")
        )
        return resp.json()

    # --- Quota operations ---

    def list_quotas(self) -> List[dict]:
        resp = self._request("GET", self._project_path("/quotas"))
        return resp.json().get("quotas", [])

    # --- IB operations ---

    def list_ib_networks(self) -> List[dict]:
        resp = self._request("GET", self._project_path("/networking/ib-networks"))
        return resp.json().get("items", [])

    def create_ib_partition(self, name: str, ib_network_id: str) -> dict:
        body = {"name": name, "ib_network_id": ib_network_id}
        resp = self._request("POST", self._project_path("/networking/ib-partitions"), body=body)
        return resp.json()

    def delete_ib_partition(self, partition_id: str) -> None:
        self._request("DELETE", self._project_path(f"/networking/ib-partitions/{partition_id}"))

    # --- Operation polling ---

    def wait_for_vm_operation(
        self, operation_id: str, timeout: float = 120, interval: float = 5
    ) -> dict:
        return self._wait_for_operation(operation_id, self.get_vm_operation, timeout, interval)

    def wait_for_disk_operation(
        self, operation_id: str, timeout: float = 30, interval: float = 2
    ) -> dict:
        return self._wait_for_operation(operation_id, self.get_disk_operation, timeout, interval)

    def _wait_for_operation(self, operation_id, get_fn, timeout, interval) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            op = get_fn(operation_id)
            state = op.get("state", op.get("operation", {}).get("state"))
            if state == "SUCCEEDED":
                return op
            if state == "FAILED":
                result = op.get("result", {})
                code = result.get("code", "")
                message = result.get("message", str(result))
                if code == "out_of_stock":
                    raise NoCapacityError(message)
                raise ProvisioningError(f"Operation {operation_id} failed: {message}")
            if time.monotonic() + interval > deadline:
                raise BackendError(f"Operation {operation_id} timed out (state: {state})")
            time.sleep(interval)


def _raise_api_error(resp: requests.Response) -> None:
    try:
        data = resp.json()
        message = data.get("message", data.get("error", str(data)))
    except Exception:
        message = resp.text[:500]
    if resp.status_code == 404:
        raise BackendError(f"Resource not found: {message}")
    raise BackendError(f"Crusoe API error ({resp.status_code}): {message}")
