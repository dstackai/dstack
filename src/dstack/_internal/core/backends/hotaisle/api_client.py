from typing import Any, Dict, Optional

import requests

from dstack._internal.core.backends.base.configurator import raise_invalid_credentials_error
from dstack._internal.core.errors import BackendError, NoCapacityError
from dstack._internal.utils.logging import get_logger

API_URL = "https://admin.hotaisle.app/api"

logger = get_logger(__name__)


class HotAisleAPIClient:
    def __init__(self, api_key: str, team_handle: str):
        self.api_key = api_key
        self.team_handle = team_handle

    def validate_api_key(self) -> bool:
        url = f"{API_URL}/user/"
        try:
            response = self._make_request("GET", url)
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response is not None:
                if e.response.status_code == 401:
                    raise_invalid_credentials_error(
                        fields=[["creds", "api_key"]], details="Invalid API key"
                    )
                if e.response.status_code == 403:
                    raise_invalid_credentials_error(
                        fields=[["creds", "api_key"]],
                        details="Authenticated user does not have required permissions",
                    )
            raise

        user_data = response.json()
        teams = user_data["teams"]
        if not teams:
            raise_invalid_credentials_error(
                fields=[["creds", "api_key"]],
                details="Valid API key but no teams found for this user",
            )

        available_teams = [team["handle"] for team in teams]
        if self.team_handle not in available_teams:
            raise_invalid_credentials_error(
                fields=[["team_handle"]],
                details=f"Team handle '{self.team_handle}' not found",
            )
        return True

    def upload_ssh_key(self, public_key: str) -> bool:
        url = f"{API_URL}/user/ssh_keys/"
        payload = {"authorized_key": public_key}

        response = self._make_request("POST", url, json=payload)

        if response.status_code == 409:
            return True  # Key already exists - success
        response.raise_for_status()
        return True

    def create_virtual_machine(self, vm_payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/"
        response = self._make_request("POST", url, json=vm_payload)
        response.raise_for_status()
        vm_data = response.json()
        return vm_data

    def get_vm_state(self, vm_name: str) -> str:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/{vm_name}/state/"
        response = self._make_request("GET", url)
        response.raise_for_status()
        state_data = response.json()
        return state_data["state"]

    def terminate_virtual_machine(self, vm_name: str) -> None:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/{vm_name}/"
        response = self._make_request(
            "DELETE",
            url,
            params={
                "force": "true",  # delete even if min reservation time not met
            },
        )
        if response.status_code == 404:
            logger.debug("Hot Aisle virtual machine %s not found", vm_name)
            return
        response.raise_for_status()

    def reserve_bare_metal_server(self, specs: Dict[str, Any], description: str) -> Dict[str, Any]:
        url = f"{API_URL}/teams/{self.team_handle}/bare_metal/"
        payload = {"specs": specs, "description": description}
        response = self._make_request("POST", url, json=payload)
        # 403: the team's bare metal server limit is reached or the API key lacks permissions.
        # 404: no available server matches the specs, e.g. another team reserved it.
        if response.status_code in [403, 404]:
            raise NoCapacityError(response.text)
        response.raise_for_status()
        return response.json()

    def get_bare_metal_server(self, server_id: str) -> Dict[str, Any]:
        url = f"{API_URL}/teams/{self.team_handle}/bare_metal/{server_id}/"
        response = self._make_request("GET", url)
        response.raise_for_status()
        return response.json()

    def release_bare_metal_server(self, server_id: str, force: bool = True) -> None:
        url = f"{API_URL}/teams/{self.team_handle}/bare_metal/{server_id}/"
        # force releases even if min reservation time not met
        params = {"force": "true"} if force else None
        response = self._make_request("DELETE", url, params=params)
        if response.status_code == 404:
            logger.debug("Hot Aisle bare metal server %s not found", server_id)
            return
        if response.status_code == 400 and not force:
            raise BackendError(
                f"Hot Aisle refused to release bare metal server {server_id}"
                f" before its minimum reservation period ends: {response.text}"
            )
        response.raise_for_status()

    def _make_request(
        self,
        method: str,
        url: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, str]] = None,
        timeout: int = 30,
    ) -> requests.Response:
        headers = {
            "accept": "application/json",
            "Authorization": f"Token {self.api_key}",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        return requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            params=params,
            timeout=timeout,
        )
