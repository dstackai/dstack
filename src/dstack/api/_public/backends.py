from typing import List

from dstack._internal.core.models.backends import BackendInfo
from dstack.api.server import APIClient


class Backend:
    def __init__(self, api_client: APIClient, backend_info: BackendInfo):
        self._api_client = api_client
        self._backend_info = backend_info

    @property
    def name(self) -> str:
        return self._backend_info.name

    def __str__(self) -> str:
        return f"<Backend '{self.name}'>"

    def __repr__(self) -> str:
        return f"<Backend '{self.name}'>"


class BackendCollection:
    """
    Operations with backends
    """

    def __init__(self, api_client: APIClient, project: str):
        self._api_client = api_client
        self._project = project

    def list(self) -> List[Backend]:
        """
        List available backends in the project

        Returns:
            backends
        """
        return [
            Backend(self._api_client, backend_info)
            for backend_info in self._api_client.projects.get(project_name=self._project).backends
        ]
