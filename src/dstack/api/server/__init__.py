from typing import Optional, Union

import requests

from dstack.api.server._backends import BackendsAPIClient
from dstack.api.server._gateways import GatewaysAPIClient
from dstack.api.server._logs import LogsAPIClient
from dstack.api.server._projects import ProjectsAPIClient
from dstack.api.server._repos import ReposAPIClient
from dstack.api.server._runs import RunsAPIClient
from dstack.api.server._secrets import SecretsAPIClient
from dstack.api.server._users import UsersAPIClient


class APIClient:
    def __init__(self, base_url: str, token: str):
        """
        :param base_url: API endpoints prefix, e.g. http://127.0.0.1:3000/
        :param token: API token
        """
        self._base_url = base_url.rstrip("/")
        self._s = requests.session()
        self._s.headers.update({"Authorization": f"Bearer {token}"})

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

    def _request(
        self, path: str, body: Optional[str] = None, raise_for_status: bool = True, **kwargs
    ) -> requests.Response:
        # TODO logging
        if body is not None:
            kwargs.setdefault("headers", {})["Content-Type"] = "application/json"
            kwargs["data"] = body
        resp = self._s.post(f"{self._base_url}/{path.lstrip('/')}", **kwargs)
        if raise_for_status:
            # TODO raise DstackError if any
            resp.raise_for_status()
        return resp
