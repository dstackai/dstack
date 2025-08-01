from typing import Any, Dict, Optional

import requests

from dstack._internal.utils.logging import get_logger

API_URL = "https://admin.hotaisle.app/api"

logger = get_logger(__name__)


class HotaisleAPIClient:
    def __init__(self, api_key: str, team_handle: str):
        self.api_key = api_key
        self.team_handle = team_handle

    def validate_api_key(self) -> bool:
        try:
            self._validate_user_and_team()
            return True
        except requests.HTTPError as e:
            if e.response.status_code in [401, 403]:
                return False
            raise e
        except ValueError:
            return False

    def _validate_user_and_team(self) -> None:
        url = f"{API_URL}/user/"
        response = self._make_request("GET", url)

        if response.ok:
            user_data = response.json()
        else:
            response.raise_for_status()

        teams = user_data.get("teams", [])
        if not teams:
            raise ValueError("No Hotaisle teams found for this user")

        available_teams = [team["handle"] for team in teams]
        if self.team_handle not in available_teams:
            raise ValueError(f"Hotaisle Team '{self.team_handle}' not found.")

    def upload_ssh_key(self, public_key: str) -> bool:
        url = f"{API_URL}/user/ssh_keys/"
        payload = {"authorized_key": public_key}

        response = self._make_request("POST", url, json=payload)

        if response.status_code == 409:
            return True  # Key already exists - success
        if not response.ok:
            response.raise_for_status()
        return True

    def create_virtual_machine(
        self, vm_payload: Dict[str, Any], instance_name: str
    ) -> Dict[str, Any]:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/"
        response = self._make_request("POST", url, json=vm_payload)

        if not response.ok:
            response.raise_for_status()

        vm_data = response.json()
        return vm_data

    def get_vm_state(self, vm_name: str) -> str:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/{vm_name}/state/"
        response = self._make_request("GET", url)

        if not response.ok:
            response.raise_for_status()

        state_data = response.json()
        return state_data["state"]

    def terminate_virtual_machine(self, vm_name: str) -> bool:
        url = f"{API_URL}/teams/{self.team_handle}/virtual_machines/{vm_name}/"
        response = self._make_request("DELETE", url)

        if response.status_code == 204:
            return True
        else:
            response.raise_for_status()

    def _make_request(
        self, method: str, url: str, json: Optional[Dict[str, Any]] = None, timeout: int = 30
    ) -> requests.Response:
        headers = {
            "accept": "application/json",
            "Authorization": self.api_key,
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        return requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=timeout,
        )
