import hashlib
from typing import Any, Dict, List, Optional

import requests
from gpuhunt.providers.jarvislabs import API_URL, JARVISLABS_REGION_URLS

from dstack._internal.core.errors import (
    BackendError,
    BackendInvalidCredentialsError,
    NoCapacityError,
)

TIMEOUT = 120


class JarvisLabsNotFoundError(BackendError):
    pass


class JarvisLabsAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def validate_api_key(self) -> bool:
        try:
            self.get_user_info()
        except BackendInvalidCredentialsError:
            return False
        return True

    def get_user_info(self) -> Dict[str, Any]:
        resp = self._make_request("GET", "users/user_info")
        if not isinstance(resp, dict):
            raise BackendError("Unexpected JarvisLabs user_info response")
        return resp

    def list_ssh_keys(self) -> List[Dict[str, Any]]:
        resp = self._make_request("GET", "ssh/")
        if isinstance(resp, list):
            return resp
        raise BackendError("Unexpected JarvisLabs SSH key list response")

    def add_ssh_key(self, public_key: str, key_name: str) -> None:
        resp = self._make_request(
            "POST",
            "ssh/",
            json={
                "ssh_key": public_key,
                "key_name": key_name,
            },
        )
        _raise_if_unsuccessful(resp, "Failed to add JarvisLabs SSH key")

    def create_ssh_key(self, public_key: str, key_name: str) -> str:
        self.add_ssh_key(public_key=public_key, key_name=key_name)
        key_id = self.find_ssh_key_id(public_key=public_key, key_name=key_name)
        if key_id is None:
            raise BackendError("Failed to find created JarvisLabs SSH key")
        return key_id

    def find_ssh_key_id(self, public_key: str, key_name: str) -> Optional[str]:
        normalized_key = _normalize_public_key(public_key)
        for ssh_key in self.list_ssh_keys():
            if str(ssh_key.get("key_name", "")) != key_name:
                continue
            if _normalize_public_key(str(ssh_key.get("ssh_key", ""))) != normalized_key:
                continue
            key_id = ssh_key.get("key_id")
            if key_id is not None:
                return str(key_id)
        return None

    def delete_ssh_key(self, key_id: str) -> None:
        try:
            resp = self._make_request("DELETE", f"ssh/{key_id}")
        except JarvisLabsNotFoundError:
            return
        _raise_if_unsuccessful(resp, "Failed to delete JarvisLabs SSH key")

    def add_ssh_key_if_needed(self, public_key: str) -> None:
        normalized_key = _normalize_public_key(public_key)
        for ssh_key in self.list_ssh_keys():
            if _normalize_public_key(str(ssh_key.get("ssh_key", ""))) == normalized_key:
                return
        key_name = _get_ssh_key_name(normalized_key)
        self.add_ssh_key(public_key=public_key, key_name=key_name)

    def create_gpu_vm(
        self,
        *,
        gpu_type: str,
        num_gpus: int,
        is_spot: bool,
        storage: int,
        region: str,
        name: str,
    ) -> str:
        resp = self._make_request(
            "POST",
            "templates/vm/create",
            region=region,
            json={
                "gpu_type": gpu_type,
                "num_gpus": num_gpus,
                "hdd": storage,
                "region": region,
                "name": name,
                "is_spot": is_spot,
                "duration": "hour",
                "disk_type": "ssd",
                "http_ports": "",
                # JarvisLabs accepts script_id for VM creates, but live CPU/GPU VM tests
                # showed it is not injected into cloud-init user-data/runcmd.
                "script_id": None,
                "script_args": "",
                "fs_id": None,
                "arguments": "",
            },
        )
        return _get_created_machine_id(resp, "GPU VM creation")

    def create_cpu_vm(
        self,
        *,
        vcpus: int,
        ram_gb: int,
        storage: int,
        region: str,
        name: str,
    ) -> str:
        resp = self._make_request(
            "POST",
            "templates/vm/cpu/create",
            region=region,
            json={
                "num_cpus": 1,
                "vcpus": vcpus,
                "ram_gb": ram_gb,
                "hdd": storage,
                "region": region,
                "name": name,
                "duration": "hour",
                "disk_type": "ssd",
                # Do not pass script_id here either; CPU VM create accepts it but ignores it.
            },
        )
        return _get_created_machine_id(resp, "CPU VM creation")

    def get_instance(self, machine_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._make_request("GET", f"users/fetch/{machine_id}")
        except JarvisLabsNotFoundError:
            return None
        if not _is_successful(resp):
            return None
        if isinstance(resp, dict):
            instance = resp.get("instance")
            if isinstance(instance, dict):
                return instance
        return None

    def get_instance_status(self, *, machine_id: str, region: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._make_request(
                "GET",
                "misc/status",
                region=region,
                params={"machine_id": machine_id},
            )
        except JarvisLabsNotFoundError:
            return None
        if isinstance(resp, dict):
            return resp
        return None

    def destroy_instance(self, *, machine_id: str, region: str) -> None:
        instance = self.get_instance(machine_id)
        if instance is None:
            return
        endpoint = "templates/vm/destroy"
        if is_cpu_vm(instance):
            endpoint = "templates/vm/cpu/destroy"
        elif _instance_template(instance) != "vm":
            endpoint = "misc/destroy"

        try:
            resp = self._make_request(
                "POST",
                endpoint,
                region=instance.get("region") or region,
                params={"machine_id": machine_id},
            )
        except JarvisLabsNotFoundError:
            return
        _raise_if_unsuccessful(resp, "Failed to destroy JarvisLabs instance")

    def _make_request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
    ) -> Any:
        try:
            response = requests.request(
                method=method,
                url=self._url(path=path, region=region),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=json,
                params=params,
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise BackendError(f"JarvisLabs request failed: {e}") from e
        if response.ok:
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as e:
                raise BackendError("Unexpected non-JSON JarvisLabs response") from e
        message = _get_response_error(response)
        if response.status_code in [401, 403]:
            raise BackendInvalidCredentialsError(fields=[["creds", "api_key"]])
        if response.status_code == 404:
            raise JarvisLabsNotFoundError(message)
        if response.status_code in [400, 409] and _looks_like_no_capacity(message):
            raise NoCapacityError(message)
        raise BackendError(message)

    def _url(self, *, path: str, region: Optional[str] = None) -> str:
        if region is None:
            base_url = API_URL
        else:
            # gpuhunt owns this allowlist because it filters JarvisLabs offers. Do not
            # fall back for unknown regions: regional VM APIs use separate hosts and
            # JarvisLabs does not expose endpoint discovery in server_meta.
            base_url = JARVISLABS_REGION_URLS.get(region)
            if base_url is None:
                raise BackendError(
                    f"Unsupported JarvisLabs region {region!r}. "
                    "JarvisLabs does not expose provisioning endpoint discovery."
                )
        return base_url.rstrip("/") + "/" + path.lstrip("/")


def is_cpu_vm(instance: Dict[str, Any]) -> bool:
    return _instance_template(instance) == "vm" and str(instance.get("gpu_type")).upper() == "CPU"


def _instance_template(instance: Dict[str, Any]) -> str:
    return str(instance.get("template") or instance.get("framework") or "").lower()


def _get_created_machine_id(resp: Any, operation: str) -> str:
    _raise_if_unsuccessful(resp, f"JarvisLabs {operation} failed")
    if isinstance(resp, dict):
        machine_id = resp.get("machine_id")
        if machine_id is not None:
            return str(machine_id)
    raise BackendError(f"JarvisLabs {operation} failed: missing machine_id")


def _raise_if_unsuccessful(resp: Any, message: str) -> None:
    if _is_successful(resp):
        return
    backend_message = _backend_message(resp)
    if _looks_like_no_capacity(backend_message):
        raise NoCapacityError(backend_message)
    raise BackendError(f"{message}: {backend_message}")


def _is_successful(resp: Any) -> bool:
    if not isinstance(resp, dict):
        return True
    if "success" in resp:
        return _coerce_bool(resp["success"])
    if "sucess" in resp:
        return _coerce_bool(resp["sucess"])
    return True


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "success"}
    return bool(value)


def _get_response_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    message = _backend_message(data)
    return message or f"HTTP {response.status_code}"


def _backend_message(resp: Any) -> str:
    if isinstance(resp, dict):
        detail = resp.get("detail")
        if isinstance(detail, list):
            return "; ".join(str(item.get("msg", item)) for item in detail)
        return str(
            resp.get("message")
            or resp.get("error")
            or resp.get("detail")
            or resp.get("msg")
            or resp
        )
    return str(resp)


def _looks_like_no_capacity(message: str) -> bool:
    message = message.lower()
    return "capacity" in message or "available" in message or "stock" in message


def _normalize_public_key(public_key: str) -> str:
    return " ".join(public_key.strip().split()[:2])


def _get_ssh_key_name(public_key: str) -> str:
    return "dstack-" + hashlib.sha1(public_key.encode()).hexdigest()[:16]
