from typing import Any, Dict, List, Optional

import requests

from dstack._internal.core.backends.base.configurator import raise_invalid_credentials_error
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class DigitalOceanAPIClient:
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.base_url = api_url

    def validate_api_key(self) -> bool:
        try:
            response = self._make_request("GET", "/v2/account")
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            status = e.response.status_code
            if status == 401:
                raise_invalid_credentials_error(
                    fields=[["creds", "api_key"]], details="Invaild API key"
                )
            raise e

    def validate_project_name(self, project_name: str) -> bool:
        if self.get_project_id(project_name) is None:
            raise_invalid_credentials_error(
                fields=[["project_name"]],
                details=f"Project with name '{project_name}' does not exist",
            )
        return True

    def list_ssh_keys(self) -> List[Dict[str, Any]]:
        response = self._make_request("GET", "/v2/account/keys")
        response.raise_for_status()
        return response.json()["ssh_keys"]

    def list_projects(self) -> List[Dict[str, Any]]:
        response = self._make_request("GET", "/v2/projects")
        response.raise_for_status()
        return response.json()["projects"]

    def get_project_id(self, project_name: str) -> Optional[str]:
        projects = self.list_projects()
        for project in projects:
            if project["name"] == project_name:
                return project["id"]
        return None

    def create_ssh_key(self, name: str, public_key: str) -> Dict[str, Any]:
        payload = {"name": name, "public_key": public_key}
        response = self._make_request("POST", "/v2/account/keys", json=payload)
        response.raise_for_status()
        return response.json()["ssh_key"]

    def get_or_create_ssh_key(self, name: str, public_key: str) -> int:
        ssh_keys = self.list_ssh_keys()
        for ssh_key in ssh_keys:
            if ssh_key["public_key"].strip() == public_key.strip():
                return ssh_key["id"]

        ssh_key = self.create_ssh_key(name, public_key)
        return ssh_key["id"]

    def create_droplet(self, droplet_config: Dict[str, Any]) -> Dict[str, Any]:
        response = self._make_request("POST", "/v2/droplets", json=droplet_config)
        if response.status_code == 422:
            raise NoCapacityError(response.json()["message"])
        response.raise_for_status()
        return response.json()["droplet"]

    def get_droplet(self, droplet_id: str) -> Dict[str, Any]:
        response = self._make_request("GET", f"/v2/droplets/{droplet_id}")
        response.raise_for_status()
        return response.json()["droplet"]

    def delete_droplet(self, droplet_id: str) -> None:
        response = self._make_request("DELETE", f"/v2/droplets/{droplet_id}")
        if response.status_code == 404:
            logger.debug("DigitalOcean droplet %s not found", droplet_id)
            return
        response.raise_for_status()

    def _make_request(
        self, method: str, endpoint: str, json: Optional[Dict[str, Any]] = None, timeout: int = 30
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=timeout,
        )
        return response
