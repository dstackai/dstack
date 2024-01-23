from typing import List

from dstack._internal.core.models.pools import Pool
from dstack.api.server import APIClient


class PoolInstance:
    def __init__(self, api_client: APIClient, pool: Pool):
        self._api_client = api_client
        self._pool = pool

    @property
    def name(self) -> str:
        return self._pool.name

    def __str__(self) -> str:
        return f"<PoolInstance '{self.name}'>"

    def __repr__(self) -> str:
        return f"<PoolInstance '{self.name}'>"


class PoolCollection:
    """
    Operations with pools
    """

    def __init__(self, api_client: APIClient, project: str):
        self._api_client = api_client
        self._project = project

    def list(self) -> List[PoolInstance]:
        """
        List available pool in the project

        Returns:
            pools
        """
        list_raw_pool = self._api_client.pool.list(project_name=self._project)
        list_pool = [PoolInstance(self._api_client, instance) for instance in list_raw_pool]
        return list_pool
