import re
from typing import Any, Optional
from urllib.parse import quote

import requests

from dstack._internal.core.errors import ComputeError

API_URL = "https://lium.io/api"
REQUEST_TIMEOUT_SECONDS = 30


class LiumAPIError(ComputeError):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        idempotent_replayed: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.idempotent_replayed = idempotent_replayed


class LiumAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_user(self) -> dict[str, Any]:
        return _object(self._make_request("GET", "/users/me"))

    def get_version(self) -> dict[str, Any]:
        return _object(self._make_request("GET", "/version"))

    def get_pods(self) -> list[dict[str, Any]]:
        return _objects(self._make_request("GET", "/pods"))

    def get_account_events(self, since: Optional[str] = None) -> list[dict[str, Any]]:
        # The account event log retains pod names and IDs after deletion.
        params: dict[str, Any] = {"limit": 1000}
        if since is not None:
            params["since"] = since
        return _objects(self._make_request("GET", "/users/me/events", params=params))

    def get_pod(self, pod_id: str) -> Optional[dict[str, Any]]:
        try:
            return _object(self._make_request("GET", f"/pods/{quote(pod_id, safe='')}"))
        except LiumAPIError as e:
            if e.status_code == 404:
                return None
            raise

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _object(self._make_request("POST", "/templates", json=payload))

    def get_templates(self) -> list[dict[str, Any]]:
        return _objects(self._make_request("GET", "/templates"))

    def delete_template(self, template_id: str) -> None:
        self._delete(f"/templates/{quote(template_id, safe='')}")

    def create_docker_credential(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _object(self._make_request("POST", "/docker-credentials/", json=payload))

    def delete_docker_credential(self, credential_id: str) -> None:
        self._delete(f"/docker-credentials/{quote(credential_id, safe='')}")

    def rent_executor(
        self, executor_id: str, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        # Retries must keep both the key and the request body unchanged. The caller
        # reconciles uncertain outcomes through the pod list before another rental.
        return _object(
            self._make_request(
                "POST",
                f"/executors/{quote(executor_id, safe='')}/rent",
                json=payload,
                headers={"Idempotency-Key": idempotency_key},
            )
        )

    def delete_pod(self, pod_id: str) -> None:
        self._delete(f"/pods/{quote(pod_id, safe='')}")

    def create_volume(self, name: str) -> dict[str, Any]:
        return _object(self._make_request("POST", "/volumes", json={"name": name}))

    def get_volumes(self) -> list[dict[str, Any]]:
        return _objects(self._make_request("GET", "/volumes"))

    def get_volume(self, volume_id: str) -> Optional[dict[str, Any]]:
        try:
            return _object(self._make_request("GET", f"/volumes/{quote(volume_id, safe='')}"))
        except LiumAPIError as e:
            if e.status_code == 404:
                return None
            raise

    def delete_volume(self, volume_id: str) -> None:
        self._delete(f"/volumes/{quote(volume_id, safe='')}")

    def _delete(self, path: str) -> None:
        try:
            self._make_request("DELETE", path)
        except LiumAPIError as e:
            if e.status_code != 404:
                raise

    def _make_request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        try:
            response = requests.request(
                method=method,
                url=API_URL + path,
                headers={"X-API-Key": self.api_key, **(headers or {})},
                json=json,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
        except requests.Timeout:
            raise LiumAPIError("Lium API request timed out") from None
        except requests.RequestException:
            raise LiumAPIError("Lium API request failed") from None
        if not 200 <= response.status_code < 300:
            code = None
            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("error"), dict):
                value = data["error"].get("code")
                if (
                    isinstance(value, str)
                    and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
                    and self.api_key not in value
                ):
                    code = value
            # Show only a short machine code; provider messages may reflect credentials.
            message = f"Lium API returned HTTP {response.status_code}"
            if code is not None:
                message += f" ({code})"
            raise LiumAPIError(
                message,
                status_code=response.status_code,
                code=code,
                idempotent_replayed=response.headers.get("Idempotent-Replayed", "").lower()
                == "true",
            )
        if method == "DELETE" or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise LiumAPIError("Lium API returned a non-JSON response") from None


def _object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LiumAPIError("Lium API returned an invalid object response")
    return data


def _objects(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise LiumAPIError("Lium API returned an invalid list response")
    return data
