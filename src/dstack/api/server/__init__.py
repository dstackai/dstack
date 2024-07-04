import os
import pprint
import time
from typing import Dict, List, Optional, Type

import requests

from dstack import version
from dstack._internal.core.errors import ClientError, ServerClientError
from dstack._internal.utils.logging import get_logger
from dstack.api.server._backends import BackendsAPIClient
from dstack.api.server._gateways import GatewaysAPIClient
from dstack.api.server._logs import LogsAPIClient
from dstack.api.server._pools import PoolAPIClient
from dstack.api.server._projects import ProjectsAPIClient
from dstack.api.server._repos import ReposAPIClient
from dstack.api.server._runs import RunsAPIClient
from dstack.api.server._secrets import SecretsAPIClient
from dstack.api.server._users import UsersAPIClient
from dstack.api.server._volumes import VolumesAPIClient

logger = get_logger(__name__)


_MAX_RETRIES = 3
_RETRY_INTERVAL = 1


class APIClient:
    """
    Low-level API client for interacting with dstack server. Implements all API endpoints

    Attributes:
        users: operations with users
        projects: operations with projects
        backends: operations with backends
        runs: operations with runs
        logs: operations with logs
        gateways: operations with gateways
        pools: operations with pools
    """

    def __init__(self, base_url: str, token: str):
        """
        Args:
            base_url: API endpoints prefix, e.g. `http://127.0.0.1:3000/`
            token: API token
        """
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._s = requests.session()
        self._s.headers.update({"Authorization": f"Bearer {token}"})
        client_api_version = os.getenv("DSTACK_CLIENT_API_VERSION", version.__version__)
        if client_api_version is not None:
            self._s.headers.update({"X-API-VERSION": client_api_version})

    @property
    def users(self) -> UsersAPIClient:
        return UsersAPIClient(self._request)

    @property
    def projects(self) -> ProjectsAPIClient:
        return ProjectsAPIClient(self._request)

    @property
    def backends(self) -> BackendsAPIClient:
        return BackendsAPIClient(self._request)

    @property
    def repos(self) -> ReposAPIClient:
        return ReposAPIClient(self._request)

    @property
    def runs(self) -> RunsAPIClient:
        return RunsAPIClient(self._request)

    @property
    def logs(self) -> LogsAPIClient:
        return LogsAPIClient(self._request)

    @property
    def secrets(self) -> SecretsAPIClient:
        return SecretsAPIClient(self._request)

    @property
    def gateways(self) -> GatewaysAPIClient:
        return GatewaysAPIClient(self._request)

    @property
    def pool(self) -> PoolAPIClient:
        return PoolAPIClient(self._request)

    @property
    def volumes(self) -> VolumesAPIClient:
        return VolumesAPIClient(self._request)

    def _request(
        self,
        path: str,
        body: Optional[str] = None,
        raise_for_status: bool = True,
        **kwargs,
    ) -> requests.Response:
        path = path.lstrip("/")
        if body is not None:
            kwargs.setdefault("headers", {})["Content-Type"] = "application/json"
            kwargs["data"] = body

        logger.debug("POST /%s", path)
        for _ in range(_MAX_RETRIES):
            try:
                # TODO: set adequate timeout here or everywhere the method is used
                resp = self._s.post(f"{self._base_url}/{path}", **kwargs)
                break
            except requests.exceptions.ConnectionError as e:
                logger.debug("Could not connect to server: %s", e)
                time.sleep(_RETRY_INTERVAL)
        else:
            raise ClientError(f"Failed to connect to dstack server {self._base_url}")

        if raise_for_status:
            if resp.status_code == 500:
                raise ClientError("Unexpected dstack server error")
            if resp.status_code == 400:  # raise ServerClientError
                detail: List[Dict] = resp.json()["detail"]
                if len(detail) == 1 and detail[0]["code"] in _server_client_errors:
                    kwargs = detail[0]
                    code = kwargs.pop("code")
                    raise _server_client_errors[code](**kwargs)
            if resp.status_code == 422:
                formatted_error = pprint.pformat(resp.json())
                raise ClientError(f"Server validation error: \n{formatted_error}")
            resp.raise_for_status()
        return resp


_server_client_errors: Dict[str, Type[ServerClientError]] = {
    cls.code: cls for cls in ServerClientError.__subclasses__()
}
_server_client_errors[ServerClientError.code] = ServerClientError
