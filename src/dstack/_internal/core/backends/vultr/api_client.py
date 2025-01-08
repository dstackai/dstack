import base64
from typing import Any, List

import requests
from requests import Response

from dstack._internal.core.errors import BackendInvalidCredentialsError

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

    def get_instance(self, instance_id: str, plan_type: str):
        if plan_type == "bare-metal":
            response = self._make_request("GET", f"/bare-metals/{instance_id}")
            return response.json()["bare_metal"]
        else:
            response = self._make_request("GET", f"/instances/{instance_id}")
            return response.json()["instance"]

    def launch_instance(
        self, region: str, plan: str, label: str, startup_script: str, public_keys: List[str]
    ):
        # Fetch or create startup script ID
        script_id: str = self.get_startup_script_id(startup_script)
        # Fetch or create SSH key IDs
        sshkey_ids: List[str] = self.get_sshkey_id(public_keys)
        # For Bare-metals
        if "vbm" in plan:
            # "Docker on Ubuntu 22.04" is required for bare-metals.
            data = {
                "region": region,
                "plan": plan,
                "label": label,
                "image_id": "docker",
                "script_id": script_id,
                "sshkey_id": sshkey_ids,
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
                "script_id": script_id,
                "sshkey_id": sshkey_ids,
            }
            resp = self._make_request("POST", "/instances", data)
            return resp.json()["instance"]["id"]
        else:
            data = {
                "region": region,
                "plan": plan,
                "label": label,
                "image_id": "docker",
                "script_id": script_id,
                "sshkey_id": sshkey_ids,
            }
            resp = self._make_request("POST", "/instances", data)
            return resp.json()["instance"]["id"]

    def get_startup_script_id(self, startup_script: str) -> str:
        script_name = "dstack-shim-script"
        encoded_script = base64.b64encode(startup_script.encode()).decode()

        # Get the list of startup scripts
        response = self._make_request("GET", "/startup-scripts")
        scripts = response.json()["startup_scripts"]

        # Find the script by name
        existing_script = next((s for s in scripts if s["name"] == script_name), None)

        if existing_script:
            # Update the existing script
            startup_id = existing_script["id"]
            update_payload = {
                "name": script_name,
                "script": encoded_script,
            }
            self._make_request("PATCH", f"/startup-scripts/{startup_id}", update_payload)
        else:
            # Create a new script
            create_payload = {
                "name": script_name,
                "type": "boot",
                "script": encoded_script,
            }
            create_response = self._make_request("POST", "/startup-scripts", create_payload)
            startup_id = create_response.json()["startup_script"]["id"]

        return startup_id

    def get_sshkey_id(self, ssh_ids: List[str]) -> List[str]:
        # Fetch existing SSH keys
        response = self._make_request("GET", "/ssh-keys")
        ssh_keys = response.json()["ssh_keys"]

        ssh_key_ids = []
        existing_keys = {key["ssh_key"]: key["id"] for key in ssh_keys}

        for ssh_key in ssh_ids:
            if ssh_key in existing_keys:
                # SSH key already exists, add its id to the list
                ssh_key_ids.append(existing_keys[ssh_key])
            else:
                # Create new SSH key
                create_payload = {"name": "dstack-ssh-key", "ssh_key": ssh_key}
                create_response = self._make_request("POST", "/ssh-keys", create_payload)
                new_ssh_key_id = create_response.json()["ssh_key"]["id"]
                ssh_key_ids.append(new_ssh_key_id)

        return ssh_key_ids

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
            raise
