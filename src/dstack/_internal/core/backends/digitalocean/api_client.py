from typing import Any, Dict, List, Optional

import requests

from dstack._internal.core.backends.base.configurator import raise_invalid_credentials_error
from dstack._internal.core.errors import BackendRateLimitExceededError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# DigitalOcean API endpoints
STANDARD_CLOUD_API_URL = "https://api.digitalocean.com/v2"
AMD_CLOUD_API_URL = "https://api-amd.digitalocean.com/v2"


class DigitalOceanAPIClient:
    def __init__(self, api_key: str, flavor: str = "standard"):
        self.api_key = api_key
        self.flavor = flavor
        self.base_url = self._get_base_url()

    def _get_base_url(self) -> str:
        if self.flavor == "amd":
            return AMD_CLOUD_API_URL
        return STANDARD_CLOUD_API_URL

    def validate_api_key(self) -> bool:
        try:
            response = self._make_request("GET", "/account")
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            status = e.response.status_code
            if status == 401:
                raise_invalid_credentials_error(
                    fields=[["creds", "api_key"]], details="Invaild API key"
                )
            raise e

    def list_ssh_keys(self) -> List[Dict[str, Any]]:
        response = self._make_request("GET", "/account/keys")
        response.raise_for_status()
        return response.json()["ssh_keys"]

    def create_ssh_key(self, name: str, public_key: str) -> Dict[str, Any]:
        payload = {"name": name, "public_key": public_key}
        response = self._make_request("POST", "/account/keys", json=payload)
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
        response = self._make_request("POST", "/droplets", json=droplet_config)
        response.raise_for_status()
        return response.json()["droplet"]

    def get_droplet(self, droplet_id: str) -> Dict[str, Any]:
        response = self._make_request("GET", f"/droplets/{droplet_id}")
        response.raise_for_status()
        return response.json()["droplet"]

    def delete_droplet(self, droplet_id: str) -> None:
        response = self._make_request("DELETE", f"/droplets/{droplet_id}")
        if response.status_code == 404:
            logger.debug("DigitalOcean droplet %s not found", droplet_id)
            return
        response.raise_for_status()

    def _make_request(
        self, method: str, endpoint: str, json: Optional[Dict[str, Any]] = None, timeout: int = 30
    ) -> requests.Response:
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=timeout,
        )

        if response.status_code == 429:
            raise BackendRateLimitExceededError("API rate limit exceeded.")

        return response
