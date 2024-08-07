from typing import Any, Dict, List, Optional

import requests

API_URL = "https://cloud.lambdalabs.com/api/v1"


class LambdaAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self.list_instance_types()
        except requests.HTTPError as e:
            if e.response.status_code in [401, 403]:
                return False
            raise e
        return True

    def list_instance_types(self):
        resp = self._make_request("GET", "/instance-types")
        if resp.ok:
            return resp.json()["data"]
        resp.raise_for_status()

    def list_instances(self) -> List[dict]:
        resp = self._make_request("GET", "/instances")
        resp.raise_for_status()
        return resp.json()["data"]

    def launch_instances(
        self,
        region_name: str,
        instance_type_name: str,
        ssh_key_names: List[str],
        file_system_names: List[str],
        quantity: int,
        name: Optional[str],
    ) -> List[str]:
        data = {
            "region_name": region_name,
            "instance_type_name": instance_type_name,
            "ssh_key_names": ssh_key_names,
            "file_system_names": file_system_names,
            "quantity": quantity,
            "name": name,
        }
        resp = self._make_request("POST", "/instance-operations/launch", data)
        if resp.ok:
            return resp.json()["data"]["instance_ids"]
        resp.raise_for_status()

    def terminate_instances(self, instance_ids: List[str]) -> List[str]:
        data = {"instance_ids": instance_ids}
        resp = self._make_request("POST", "/instance-operations/terminate", data)
        if resp.ok:
            return resp.json()["data"]
        resp.raise_for_status()

    def list_ssh_keys(self) -> List[Dict]:
        resp = self._make_request("GET", "/ssh-keys")
        if resp.ok:
            return resp.json()["data"]
        resp.raise_for_status()

    def add_ssh_key(self, name: str, public_key: str) -> List[Dict]:
        data = {
            "name": name,
            "public_key": public_key,
        }
        resp = self._make_request("POST", "/ssh-keys", data)
        if resp.ok:
            return resp.json()["data"]
        resp.raise_for_status()

    def _make_request(self, method: str, path: str, data: Any = None):
        # TODO: fix S113 by setting an adequate timeout here or in every method
        return requests.request(  # noqa: S113
            method=method,
            url=API_URL + path,
            json=data,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _url(self, path: str) -> str:
        return API_URL + path
