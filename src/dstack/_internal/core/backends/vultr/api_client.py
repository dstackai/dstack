import base64
from typing import Any, Optional

import requests
from requests import Response

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError

API_URL = "https://api.vultr.com/v2"


class VultrApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self._make_request("GET", "/ssh-keys")
        except BackendInvalidCredentialsError:
            return False
        return True

    def get_instance(self, instance_id: str, plan_type: str) -> dict:
        if plan_type == "bare-metal":
            response = self._make_request("GET", f"/bare-metals/{instance_id}")
            return response.json()["bare_metal"]
        else:
            response = self._make_request("GET", f"/instances/{instance_id}")
            return response.json()["instance"]

    def get_vpc_for_region(self, region: str) -> Optional[dict]:
        response = self._make_request("GET", "/vpcs?per_page=500")
        vpcs = response.json().get("vpcs", [])
        if vpcs:
            for vpc in vpcs:
                if vpc["description"] == f"dstack-vpc-{region}":
                    return vpc
        return None

    def create_vpc(self, region: str) -> dict:
        data = {"region": region, "description": f"dstack-vpc-{region}"}
        response = self._make_request("POST", "/vpcs", data=data)
        return response.json()["vpc"]

    def launch_instance(self, region: str, plan: str, label: str, user_data: str, vpc_id: str):
        # For Bare-metals
        if "vbm" in plan:
            # "Docker on Ubuntu 22.04" is required for bare-metals.
            data = {
                "region": region,
                "plan": plan,
                "label": label,
                "image_id": "docker",
                "user_data": base64.b64encode(user_data.encode()).decode(),
                "attach_vpc": [vpc_id],
            }
            resp = self._make_request("POST", "/bare-metals", data)
            return resp.json()["bare_metal"]["id"]
        # For VMs
        elif "vcg" in plan:
            # Ubuntu 22.04 will be installed. For gpu VMs, docker is preinstalled.
            data = {
                "region": region,
                "plan": plan,
                "label": label,
                "os_id": 1743,
                "user_data": base64.b64encode(user_data.encode()).decode(),
                "attach_vpc": [vpc_id],
            }
            resp = self._make_request("POST", "/instances", data)
            return resp.json()["instance"]["id"]
        else:
            data = {
                "region": region,
                "plan": plan,
                "label": label,
                "image_id": "docker",
                "user_data": base64.b64encode(user_data.encode()).decode(),
                "attach_vpc": [vpc_id],
            }
            resp = self._make_request("POST", "/instances", data)
            return resp.json()["instance"]["id"]

    def terminate_instance(self, instance_id: str, plan_type: str):
        if plan_type == "bare-metal":
            # Terminate bare-metal instance
            endpoint = f"/bare-metals/{instance_id}"
        else:
            # Terminate virtual machine instance
            endpoint = f"/instances/{instance_id}"
        self._make_request("DELETE", endpoint)

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
            if e.response is not None and e.response.status_code in (
                requests.codes.bad_request,
                requests.codes.internal_server_error,
                requests.codes.not_found,
            ):
                raise BackendError(e.response.text)
            raise
