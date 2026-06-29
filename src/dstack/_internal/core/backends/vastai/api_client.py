import json
import threading
import time
from typing import List, Optional, Union

import requests
from requests.adapters import HTTPAdapter, Retry

import dstack._internal.utils.docker as docker
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.common import RegistryAuth

# v1 instances list is paginated; max enforced server-side is 25 per page.
_V1_INSTANCES_PAGE_LIMIT = 25


class VastAIAPIClient:
    def __init__(self, api_key: str):
        self.api_url_v0 = "https://console.vast.ai/api/v0"
        self.api_url_v1 = "https://console.vast.ai/api/v1"
        self.api_key = api_key
        self.s = requests.Session()  # TODO: set adequate timeout everywhere the session is used
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 504],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.s.mount(prefix=f"{self.api_url_v0}/instances/", adapter=adapter)
        self.s.mount(prefix=f"{self.api_url_v1}/instances/", adapter=adapter)
        self.lock = threading.Lock()
        self.instances_cache_ts: float = 0
        self.instances_cache: List[dict] = []

    def get_bundle(self, bundle_id: Union[str, int]) -> Optional[dict]:
        resp = self.s.post(self._url_v0("/bundles/"), json={"id": {"eq": bundle_id}})
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
        resp = self.s.put(self._url_v0(f"/asks/{bundle_id}/"), json=payload)
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
        resp = self.s.delete(self._url_v0(f"/instances/{instance_id}/"))
        if resp.status_code != 200 or not resp.json()["success"]:
            return False
        self._invalidate_cache()
        return True

    def get_instances(self, cache_ttl: float = 3.0) -> List[dict]:
        with self.lock:
            if time.time() - self.instances_cache_ts > cache_ttl:
                self.instances_cache = self._list_instances_v1()
                self.instances_cache_ts = time.time()
            return self.instances_cache

    def get_instance(self, instance_id: Union[str, int]) -> Optional[dict]:
        instances = self._list_instances_v1(
            select_filters={"id": {"eq": int(instance_id)}}, limit=1
        )
        return instances[0] if instances else None

    def request_logs(self, instance_id: Union[str, int]) -> dict:
        resp = self.s.put(
            self._url_v0(f"/instances/request_logs/{instance_id}/"), json={"tail": "1000"}
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

    def _list_instances_v1(
        self,
        select_filters: Optional[dict] = None,
        limit: int = _V1_INSTANCES_PAGE_LIMIT,
    ) -> List[dict]:
        """Page through the v1 instances endpoint and return all matches.

        The v1 endpoint enforces keyset pagination with a max of 25 results
        per response, so we follow `next_token` until the server stops
        returning one.
        """
        page_limit = max(1, min(limit, _V1_INSTANCES_PAGE_LIMIT))
        params: dict = {
            "limit": page_limit,
            "select_filters": json.dumps(select_filters or {}),
        }
        instances: List[dict] = []
        while True:
            resp = self.s.get(self._url_v1("/instances/"), params=params)
            resp.raise_for_status()
            data = resp.json()
            instances.extend(data.get("instances", []))
            next_token = data.get("next_token")
            if not next_token:
                break
            params["after_token"] = next_token
        return instances

    def _url_v0(self, path: str) -> str:
        return f"{self.api_url_v0}/{path.lstrip('/')}?api_key={self.api_key}"

    def _url_v1(self, path: str) -> str:
        return f"{self.api_url_v1}/{path.lstrip('/')}?api_key={self.api_key}"

    def _invalidate_cache(self):
        with self.lock:
            self.instances_cache_ts = 0
            self.instances_cache = []
