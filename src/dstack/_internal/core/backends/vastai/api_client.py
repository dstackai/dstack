from typing import Optional, Union

import requests

import dstack._internal.utils.docker as docker
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.common import RegistryAuth


class VastAIRateLimitError(Exception):
    pass


class VastAICreateInstanceError(Exception):
    """
    Attributes:
        resp: Full API response.
        created_instance_id: ID of the instance that was created despite the error. For example,
            Vast.ai creates spot instances in the stopped state and returns an error if the bid is
            insufficient.
    """

    def __init__(
        self, *args, resp: str, created_instance_id: Optional[int] = None, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.resp = resp
        self.created_instance_id = created_instance_id


class VastAIAPIClient:
    def __init__(self, api_key: str):
        self.api_url = "https://console.vast.ai/api"
        self.api_key = api_key
        self.s = requests.Session()  # TODO: set adequate timeout everywhere the session is used

    def create_instance(
        self,
        instance_name: str,
        bundle_id: Union[str, int],
        image_name: str,
        onstart: str,
        disk_size: int,
        registry_auth: Optional[RegistryAuth] = None,
        bid: Optional[float] = None,
    ) -> int:
        """
        Args:
            instance_name: instance label
            bundle_id: desired host
            image_name: docker image name
            onstart: commands to run on start
            registry_auth: registry auth credentials for private images
            bid: per-machine bid price in $/hour. If set, an interruptible
                (spot) instance is created; if None, an on-demand instance.

        Raises:
            VastAICreateInstanceError: if instance cannot be created

        Returns:
            Instance ID
        """
        image_login = None
        if registry_auth:
            registry = docker.parse_image_name(image_name).registry or "docker.io"
            image_login = f"-u {registry_auth.username} -p {registry_auth.password} {registry}"
        payload = {
            "client_id": "me",
            "image": image_name,
            "price": bid,
            "disk": disk_size,
            "label": instance_name,
            "env": {
                f"-p {DSTACK_RUNNER_SSH_PORT}:{DSTACK_RUNNER_SSH_PORT}": "1",
            },
            "user": "root",
            "onstart": "/bin/sh",
            "args": ["-c", onstart],
            "runtype": "args",
            "image_login": image_login,
            "python_utf8": False,
            "lang_utf8": False,
            "use_jupyter_lab": False,
            "jupyter_dir": None,
            "create_from": None,
            "force": False,
        }
        resp = self.s.put(self._url(f"/v0/asks/{bundle_id}/"), json=payload)
        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            raise VastAICreateInstanceError(resp=resp.text)
        if resp.status_code != 200 or not data["success"]:
            raise VastAICreateInstanceError(
                resp=resp.text, created_instance_id=data.get("new_contract")
            )
        return data["new_contract"]

    def destroy_instance(self, instance_id: Union[str, int]) -> None:
        resp = self.s.delete(self._url(f"/v0/instances/{instance_id}/"))
        if resp.status_code == 429:
            raise VastAIRateLimitError()
        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            raise ComputeError(resp.text)
        if resp.status_code != 200 or not data["success"]:
            if data.get("error") != "no_such_instance":
                raise ComputeError(resp.text)

    def get_instance(self, instance_id: Union[str, int]) -> Optional[dict]:
        resp = self.s.get(self._url(f"/v0/instances/{instance_id}/"))
        if resp.status_code == 429:
            raise VastAIRateLimitError()
        resp.raise_for_status()
        data = resp.json()
        return data["instances"]

    def auth_test(self) -> bool:
        try:
            self.s.get(self._url("/v1/instances/")).raise_for_status()
            return True
        except requests.HTTPError:
            return False

    def _url(self, path):
        return f"{self.api_url}/{path.lstrip('/')}?api_key={self.api_key}"
