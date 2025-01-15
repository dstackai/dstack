import threading
import time
from typing import List, Optional, Union

import requests
from requests.adapters import HTTPAdapter, Retry

import dstack._internal.server.services.docker as docker
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.common import RegistryAuth


class VastAIAPIClient:
    def __init__(self, api_key: str):
        self.api_url = "https://console.vast.ai/api/v0".rstrip("/")
        self.api_key = api_key
        self.s = requests.Session()  # TODO: set adequate timeout everywhere the session is used
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 504],
        )
        self.s.mount(prefix=self._url("/instances/"), adapter=HTTPAdapter(max_retries=retries))
        self.lock = threading.Lock()
        self.instances_cache_ts: float = 0
        self.instances_cache: List[dict] = []

    def get_bundle(self, bundle_id: Union[str, int]) -> Optional[dict]:
        resp = self.s.post(self._url("/bundles/"), json={"id": {"eq": bundle_id}})
        resp.raise_for_status()
        data = resp.json()
        offers = data["offers"]
        return offers[0] if offers else None

    def create_instance(
        self,
        instance_name: str,
        bundle_id: Union[str, int],
        image_name: str,
        onstart: str,
        disk_size: int,
        registry_auth: Optional[RegistryAuth] = None,
    ) -> dict:
        """
        Args:
            instance_name: instance label
            bundle_id: desired host
            image_name: docker image name
            onstart: commands to run on start
            registry_auth: registry auth credentials for private images

        Raises:
            NoCapacityError: if instance cannot be created

        Returns:
            create instance response
        """
        image_login = None
        if registry_auth:
            registry = docker.parse_image_name(image_name).registry or "docker.io"
            image_login = f"-u {registry_auth.username} -p {registry_auth.password} {registry}"
        payload = {
            "client_id": "me",
            "image": image_name,
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
        resp = self.s.put(self._url(f"/asks/{bundle_id}/"), json=payload)
        if resp.status_code != 200 or not (data := resp.json())["success"]:
            raise NoCapacityError(resp.text)
        self._invalidate_cache()
        return data

    def destroy_instance(self, instance_id: Union[str, int]) -> bool:
        """
        Args:
            instance_id: instance to destroy

        Returns:
            True if instance was destroyed successfully
        """
        resp = self.s.delete(self._url(f"/instances/{instance_id}/"))
        if resp.status_code != 200 or not resp.json()["success"]:
            return False
        self._invalidate_cache()
        return True

    def get_instances(self, cache_ttl: float = 3.0) -> List[dict]:
        with self.lock:
            if time.time() - self.instances_cache_ts > cache_ttl:
                resp = self.s.get(self._url("/instances/"))
                resp.raise_for_status()
                data = resp.json()
                self.instances_cache_ts = time.time()
                self.instances_cache = data["instances"]
            return self.instances_cache

    def get_instance(self, instance_id: Union[str, int]) -> Optional[dict]:
        instances = self.get_instances()
        for instance in instances:
            if instance["id"] == int(instance_id):
                return instance
        return None

    def request_logs(self, instance_id: Union[str, int]) -> dict:
        resp = self.s.put(
            self._url(f"/instances/request_logs/{instance_id}/"), json={"tail": "1000"}
        )
        resp.raise_for_status()
        data = resp.json()
        if not data["success"]:
            raise requests.HTTPError(data)
        return data

    def auth_test(self) -> bool:
        try:
            self.get_instances()
            return True
        except requests.HTTPError:
            return False

    def _url(self, path):
        return f"{self.api_url}/{path.lstrip('/')}?api_key={self.api_key}"

    def _invalidate_cache(self):
        with self.lock:
            self.instances_cache_ts = 0
            self.instances_cache = []
