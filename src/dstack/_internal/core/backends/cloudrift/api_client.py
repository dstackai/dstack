import os
import re
from typing import Any, Dict, List, Mapping, Optional, Union

import requests
from packaging import version
from requests import Response

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


CLOUDRIFT_SERVER_ADDRESS = "https://api.cloudrift.ai"
CLOUDRIFT_API_VERSION = "2025-05-29"


class RiftClient:
    def __init__(self, api_key: Optional[str] = None):
        self.public_api_root = os.path.join(CLOUDRIFT_SERVER_ADDRESS, "api/v1")
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        """
        Validates the API key by making a request to the server.
        Returns True if the API key is valid, False otherwise.
        """
        try:
            response = self._make_request("auth/me")
            if isinstance(response, dict):
                return "email" in response
            return False
        except BackendInvalidCredentialsError:
            return False
        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return False

    def get_instance_types(self) -> List[Dict]:
        request_data = {"selector": {"ByServiceAndLocation": {"services": ["vm"]}}}
        response_data = self._make_request("instance-types/list", request_data)
        if isinstance(response_data, dict):
            return response_data.get("instance_types", [])
        return []

    def list_recipes(self) -> List[Dict]:
        request_data = {}
        response_data = self._make_request("recipes/list", request_data)
        if isinstance(response_data, dict):
            return response_data.get("groups", [])
        return []

    def get_vm_recipies(self) -> List[Dict]:
        """
        Retrieves a list of VM recipes from the CloudRift API.
        Returns a list of dictionaries containing recipe information.
        """
        recipe_group = self.list_recipes()
        vm_recipes = []
        for group in recipe_group:
            tags = group.get("tags", [])
            has_vm = "vm" in map(str.lower, tags)
            if group.get("name", "").lower() != "linux" or not has_vm:
                continue

            recipes = group.get("recipes", [])
            for recipe in recipes:
                details = recipe.get("details", {})
                if details.get("VirtualMachine", False):
                    vm_recipes.append(recipe)

        return vm_recipes

    def get_vm_image_url(self) -> Optional[str]:
        recipes = self.get_vm_recipies()
        ubuntu_images = []
        for recipe in recipes:
            has_nvidia_driver = "nvidia-driver" in recipe.get("tags", [])
            if not has_nvidia_driver:
                continue

            recipe_name = recipe.get("name", "")
            if "Ubuntu" not in recipe_name:
                continue

            url = recipe["details"].get("VirtualMachine", {}).get("image_url", None)
            version_match = re.search(r".* (\d+\.\d+)", recipe_name)
            if url and version_match and version_match.group(1):
                ubuntu_version = version.parse(version_match.group(1))
                ubuntu_images.append((ubuntu_version, url))

        ubuntu_images.sort(key=lambda x: x[0])  # Sort by version
        if ubuntu_images:
            return ubuntu_images[-1][1]

        return None

    def deploy_instance(
        self, instance_type: str, region: str, ssh_keys: List[str], cmd: str
    ) -> List[str]:
        image_url = self.get_vm_image_url()
        if not image_url:
            raise BackendError("No suitable VM image found.")

        request_data = {
            "config": {
                "VirtualMachine": {
                    "cloudinit_commands": cmd,
                    "image_url": image_url,
                    "ssh_key": {"PublicKeys": ssh_keys},
                }
            },
            "selector": {
                "ByInstanceTypeAndLocation": {
                    "datacenters": [region],
                    "instance_type": instance_type,
                }
            },
            "with_public_ip": True,
        }
        logger.debug("Deploying instance with request data: %s", request_data)

        response_data = self._make_request("instances/rent", request_data)
        if isinstance(response_data, dict):
            return response_data.get("instance_ids", [])
        return []

    def list_instances(self, instance_ids: Optional[List[str]] = None) -> List[Dict]:
        request_data = {
            "selector": {
                "ByStatus": ["Initializing", "Active", "Deactivating"],
            }
        }
        logger.debug("Listing instances with request data: %s", request_data)
        response_data = self._make_request("instances/list", request_data)
        if isinstance(response_data, dict):
            return response_data.get("instances", [])

        return []

    def get_instance_by_id(self, instance_id: str) -> Optional[Dict]:
        request_data = {"selector": {"ById": [instance_id]}}
        logger.debug("Getting instance with request data: %s", request_data)
        response_data = self._make_request("instances/list", request_data)
        if isinstance(response_data, dict):
            instances = response_data.get("instances", [])
            if isinstance(instances, list) and len(instances) > 0:
                return instances[0]

        return None

    def terminate_instance(self, instance_id: str) -> bool:
        request_data = {"selector": {"ById": [instance_id]}}
        logger.debug("Terminating instance with request data: %s", request_data)
        response_data = self._make_request("instances/terminate", request_data)
        if isinstance(response_data, dict):
            logger.debug("Terminating instance with response: %s", response_data)
            info = response_data.get("terminated", [])
            is_terminated = len(info) > 0
            if not is_terminated:
                # check if the instance is already terminated
                instance_info = self.get_instance_by_id(instance_id)
                is_terminated = instance_info is None or instance_info.get("status") == "Inactive"
                logger.debug(
                    "Instance %s is already terminated: %s response: %s",
                    instance_id,
                    is_terminated,
                    instance_info,
                )
            return is_terminated

        return False

    def _make_request(
        self,
        endpoint: str,
        data: Optional[Mapping[str, Any]] = None,
        method: str = "POST",
        **kwargs,
    ) -> Union[Mapping[str, Any], str, Response]:
        headers = {}
        if self.api_key is not None:
            headers["X-API-Key"] = self.api_key

        version = CLOUDRIFT_API_VERSION
        full_url = f"{self.public_api_root}/{endpoint}"

        try:
            response = requests.request(
                method,
                full_url,
                headers=headers,
                json={"version": version, "data": data},
                timeout=15,
                **kwargs,
            )

            if not response.ok:
                response.raise_for_status()
            try:
                response_json = response.json()
                if isinstance(response_json, str):
                    return response_json
                if version is not None and version < response_json["version"]:
                    logger.warning(
                        "The API version %s is lower than the server version %s. ",
                        version,
                        response_json["version"],
                    )
                return response_json["data"]
            except requests.exceptions.JSONDecodeError:
                return response
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (
                requests.codes.forbidden,
                requests.codes.unauthorized,
            ):
                raise BackendInvalidCredentialsError(e.response.text)
            raise
