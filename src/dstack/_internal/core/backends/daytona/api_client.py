import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit

import requests
from gpuhunt.providers.daytona import API_URL

from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError

TIMEOUT = 30


class DaytonaAPIError(BackendError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class DaytonaNotFoundError(DaytonaAPIError):
    pass


class DaytonaAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_current_api_key(self) -> Dict[str, Any]:
        return _object(self._make_request("GET", "/api-keys/current"))

    def get_organization_usage(self, organization_id: str) -> Dict[str, Any]:
        return _object(
            self._make_request("GET", f"/organizations/{_path_id(organization_id)}/usage")
        )

    def get_available_sandbox_classes(self, organization_id: str) -> List[Dict[str, Any]]:
        return _objects(
            self._make_request(
                "GET", f"/organizations/{_path_id(organization_id)}/available-sandbox-classes"
            )
        )

    def get_shared_regions(self) -> List[Dict[str, Any]]:
        return _objects(self._make_request("GET", "/shared-regions"))

    def create_sandbox(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Do not retry creates: a lost response does not mean the sandbox was not created.
        return _object(self._make_request("POST", "/sandbox", json=payload))

    def get_sandbox(self, sandbox_id_or_name: str) -> Optional[Dict[str, Any]]:
        try:
            return _object(self._make_request("GET", f"/sandbox/{_path_id(sandbox_id_or_name)}"))
        except DaytonaNotFoundError:
            return None

    def delete_sandbox(self, sandbox_id_or_name: str) -> None:
        self._delete(f"/sandbox/{_path_id(sandbox_id_or_name)}")

    def create_registry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _object(self._make_request("POST", "/docker-registry", json=payload))

    def get_registries(self) -> List[Dict[str, Any]]:
        return _objects(self._make_request("GET", "/docker-registry"))

    def delete_registry(self, registry_id: str) -> None:
        self._delete(f"/docker-registry/{_path_id(registry_id)}")

    def create_volume(self, name: str) -> Dict[str, Any]:
        return _object(self._make_request("POST", "/volumes", json={"name": name}))

    def get_volume(self, volume_id: str) -> Optional[Dict[str, Any]]:
        try:
            return _object(self._make_request("GET", f"/volumes/{_path_id(volume_id)}"))
        except DaytonaNotFoundError:
            return None

    def get_volume_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            return _object(self._make_request("GET", f"/volumes/by-name/{_path_id(name)}"))
        except DaytonaNotFoundError:
            return None

    def delete_volume(self, volume_id: str) -> None:
        self._delete(f"/volumes/{_path_id(volume_id)}")

    def get_toolbox_url(self, sandbox_id: str) -> str:
        data = _object(
            self._make_request("GET", f"/sandbox/{_path_id(sandbox_id)}/toolbox-proxy-url")
        )
        proxy_url = data.get("url")
        if not isinstance(proxy_url, str):
            raise DaytonaAPIError("Daytona returned an invalid toolbox proxy URL")
        _validate_toolbox_url(proxy_url)
        # The API returns the proxy base; Toolbox routes also need the sandbox ID.
        return f"{proxy_url.rstrip('/')}/{_path_id(sandbox_id)}"

    def get_session(self, toolbox_url: str, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            return _object(
                self._make_toolbox_request(
                    "GET", toolbox_url, f"/process/session/{_path_id(session_id)}"
                )
            )
        except DaytonaNotFoundError:
            return None

    def create_session(self, toolbox_url: str, session_id: str) -> None:
        self._make_toolbox_request(
            "POST", toolbox_url, "/process/session", json={"sessionId": session_id}
        )

    def execute_session_command(
        self,
        toolbox_url: str,
        session_id: str,
        command: str,
        *,
        run_async: bool = True,
    ) -> Dict[str, Any]:
        return _object(
            self._make_toolbox_request(
                "POST",
                toolbox_url,
                f"/process/session/{_path_id(session_id)}/exec",
                json={"command": command, "runAsync": run_async},
            )
        )

    def create_ssh_access(
        self, sandbox_id_or_name: str, *, expires_in_minutes: int
    ) -> Dict[str, Any]:
        if expires_in_minutes <= 0:
            raise ValueError("SSH access lifetime must be positive")
        return _object(
            self._make_request(
                "POST",
                f"/sandbox/{_path_id(sandbox_id_or_name)}/ssh-access",
                params={"expiresInMinutes": expires_in_minutes},
            )
        )

    def _delete(self, path: str) -> None:
        # Deletes are idempotent. Retry transient failures, including during rollback
        # when the server has not yet persisted the resource's provisioning data.
        for attempt in range(3):
            try:
                self._make_request("DELETE", path)
                return
            except DaytonaNotFoundError:
                return
            except DaytonaAPIError as e:
                if attempt == 2 or (
                    e.status_code is not None
                    and e.status_code not in (408, 429)
                    and e.status_code < 500
                ):
                    raise
                time.sleep(attempt + 1)

    def _make_request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._request(method, API_URL + path, json=json, params=params)

    def _make_toolbox_request(
        self,
        method: str,
        toolbox_url: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        _validate_toolbox_url(toolbox_url)
        return self._request(method, toolbox_url.rstrip("/") + path, json=json)

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        try:
            response = requests.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=json,
                params=params,
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.Timeout as e:
            raise DaytonaAPIError("Daytona API request timed out") from e
        except requests.RequestException as e:
            raise DaytonaAPIError("Daytona API request failed") from e
        if response.status_code == 401:
            raise BackendInvalidCredentialsError(fields=[["creds", "api_key"]])
        if not 200 <= response.status_code < 300:
            message = _response_message(response)
            if self.api_key:
                message = message.replace(self.api_key, "[redacted]")
            error = DaytonaNotFoundError if response.status_code == 404 else DaytonaAPIError
            raise error(message, status_code=response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise DaytonaAPIError("Daytona API returned a non-JSON response") from e


def _object(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise DaytonaAPIError("Daytona API returned an invalid object response")
    return data


def _objects(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise DaytonaAPIError("Daytona API returned an invalid list response")
    return data


def _path_id(value: str) -> str:
    return quote(value, safe="")


def _validate_toolbox_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.endswith((".daytona.io", ".daytona.work"))
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise DaytonaAPIError("Daytona returned an invalid toolbox proxy URL")


def _response_message(response: requests.Response) -> str:
    message = f"Daytona API returned HTTP {response.status_code}"
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        for field in ("message", "error", "detail"):
            value = data.get(field)
            if isinstance(value, str) and value:
                return f"{message}: {value}"
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return f"{message}: {'; '.join(value)}"
    # Do not include arbitrary HTML/text responses, which can reflect request credentials.
    return message
