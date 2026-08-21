import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from dstack._internal.core.errors import (
    BackendError,
    BackendInvalidCredentialsError,
    NoCapacityError,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://api.seeweb.it/ecs/v2"
TIMEOUT = 30


@dataclass(frozen=True)
class SeewebPlanAvailability:
    regions: frozenset[str]
    images: tuple[str, ...]


class SeewebApiClient:
    """Minimal client for the Seeweb ECS REST API (https://api.seeweb.it/ecs/v2).

    Uses ``requests`` directly instead of the ``ecsapi`` SDK: ``ecsapi`` requires pydantic v2,
    while dstack is pinned to pydantic v1, so the two cannot share an environment.
    """

    def __init__(self, api_token: str):
        self.api_token = api_token

    def _request(
        self, method: str, path: str, json: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        try:
            response = requests.request(
                method=method,
                url=API_URL + path,
                headers={"X-APITOKEN": self.api_token},
                json=json,
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise BackendError(f"Seeweb API request failed: {e}") from e
        if response.status_code in (requests.codes.unauthorized, requests.codes.forbidden):
            raise BackendInvalidCredentialsError(_response_message(response))
        return response

    def validate_api_key(self) -> bool:
        try:
            response = self._request("GET", "/regions")
        except BackendInvalidCredentialsError:
            return False
        _raise_api_error(response)
        return True

    def get_or_create_ssh_key(self, public_key: str) -> str:
        """Return the label of a Seeweb SSH key matching ``public_key``, creating it if needed."""
        canonical_key = _canonicalize_ssh_public_key(public_key)
        label = "dstack-" + hashlib.sha256(canonical_key.encode()).hexdigest()[:20]
        response = self._request("GET", "/sshkeys")
        data = _response_data(response)
        for key in data.get("pubkeys", []):
            if not isinstance(key, dict):
                continue
            try:
                existing_key = _canonicalize_ssh_public_key(str(key.get("key", "")))
            except ValueError:
                continue
            if existing_key == canonical_key:
                existing_label = key.get("label")
                if isinstance(existing_label, str):
                    return existing_label
        created = self._request(
            "POST",
            "/sshkeys",
            json={"key": public_key.strip(), "label": label},
        )
        _response_data(created)
        return label

    def get_available_plans(self) -> dict[str, SeewebPlanAvailability]:
        """Return current regions and allowed images for each activatable plan."""
        response = self._request("GET", "/plans/availables")
        data = _response_data(response)
        available = {}
        for plan in data.get("plans", []):
            if not isinstance(plan, dict) or not isinstance(plan.get("name"), str):
                continue
            regions = set()
            raw_regions = plan.get("region_availables") or plan.get("region_available") or []
            if isinstance(raw_regions, list):
                for region in raw_regions:
                    if isinstance(region, dict) and isinstance(region.get("region"), str):
                        regions.add(region["region"])
            images = []
            raw_images = plan.get("os_availables") or []
            if isinstance(raw_images, list):
                for image in raw_images:
                    if (
                        isinstance(image, dict)
                        and isinstance(image.get("name"), str)
                        and image.get("active_flag") is not False
                    ):
                        images.append(image["name"])
            available[plan["name"]] = SeewebPlanAvailability(
                regions=frozenset(regions),
                images=tuple(images),
            )
        return available

    def get_available_plan_regions(self) -> set[tuple[str, str]]:
        """Return the set of ``(plan_name, region)`` pairs that can currently be provisioned.

        Seeweb's ``/plans`` catalog lists a plan's regions, but a plan/region is only actually
        creatable if it appears in ``/plans/availables`` ``region_availables`` (i.e. has capacity).
        """
        return {
            (plan_name, region)
            for plan_name, availability in self.get_available_plans().items()
            for region in availability.regions
        }

    def create_server(self, body: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[int]]:
        """Create a server. Returns ``(server_dict, action_id)``.

        Capacity errors become ``NoCapacityError`` so dstack can fall through to another offer.
        """
        response = self._request("POST", "/servers", json=body)
        data = _response_data(response, capacity_errors=True)
        if not isinstance(data, dict) or "server" not in data:
            raise BackendError("Seeweb create-server response did not include a server")
        server = data["server"]
        if not isinstance(server, dict) or not isinstance(server.get("name"), str):
            raise BackendError("Seeweb create-server response contained an invalid server")
        action = data.get("action_id", data.get("action"))
        if isinstance(action, dict):
            action = action.get("id")
        action_id = action if isinstance(action, int) else None
        return server, action_id

    def get_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        response = self._request("GET", f"/actions/{action_id}")
        if response.status_code == requests.codes.not_found:
            return None
        data = _response_data(response)
        action = data.get("action")
        return action if isinstance(action, dict) else None

    def get_server(self, name: str) -> Optional[Dict[str, Any]]:
        response = self._request("GET", f"/servers/{name}")
        if response.status_code == requests.codes.not_found:
            return None
        data = _response_data(response)
        server = data.get("server")
        return server if isinstance(server, dict) else None

    def delete_server(self, name: str) -> None:
        """Delete a server, treating a missing server as success (idempotent)."""
        response = self._request("DELETE", f"/servers/{name}")
        if response.status_code == requests.codes.not_found:
            logger.debug("Seeweb server %s already deleted", name)
            return
        _response_data(response)


def _response_data(
    response: requests.Response, *, capacity_errors: bool = False
) -> Dict[str, Any]:
    try:
        data = response.json()
    except requests.JSONDecodeError as e:
        if not response.ok:
            raise BackendError(_response_message(response)) from e
        raise BackendError("Seeweb API returned a non-JSON response") from e
    if not isinstance(data, dict):
        raise BackendError("Seeweb API returned an invalid response")
    status = str(data.get("status", "ok")).lower()
    if not response.ok or status not in {"ok", "success"}:
        message = _response_message(response, data)
        if capacity_errors and _is_capacity_error(message):
            raise NoCapacityError(message)
        raise BackendError(message)
    return data


def _raise_api_error(response: requests.Response) -> None:
    _response_data(response)


def _response_message(response: requests.Response, data: Optional[Dict[str, Any]] = None) -> str:
    if data is None:
        try:
            parsed = response.json()
            data = parsed if isinstance(parsed, dict) else None
        except requests.JSONDecodeError:
            data = None
    if data is not None:
        for field in ("message", "error", "detail"):
            value = data.get(field)
            if value:
                return str(value)
    text = response.text.strip()
    return text if text else f"Seeweb API returned HTTP {response.status_code}"


def _is_capacity_error(message: str) -> bool:
    normalized = message.lower()
    return any(
        marker in normalized
        for marker in (
            "not available",
            "no capacity",
            "lack of resources",
            "not activatable",
            "no host",
        )
    )


def _canonicalize_ssh_public_key(public_key: str) -> str:
    parts = public_key.strip().split()
    if len(parts) < 2 or not (
        parts[0].startswith("ssh-") or parts[0].startswith("ecdsa-") or parts[0].startswith("sk-")
    ):
        raise ValueError("Invalid SSH public key")
    return " ".join(parts[:2])
