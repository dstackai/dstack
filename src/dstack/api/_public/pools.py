from typing import List

from dstack.api.server import APIClient


class Instance:
    def __init__(self, api_client: APIClient, instance):
        self._api_client = api_client
        self._instance = instance

    @property
    def name(self) -> str:
        return self._instance.name

    def __str__(self) -> str:
        return f"<Instance '{self.name}'>"

    def __repr__(self) -> str:
        return f"<Instance '{self.name}'>"


class PoolCollection:
    """
    Operations with pools
    """

    def __init__(self, api_client: APIClient, project: str):
        self._api_client = api_client
        self._project = project

    def list(self) -> List[Instance]:
        """
        List available pool in the project

        Returns:
            pools
        """
        list_raw_instances = self._api_client.pool.list(project_name=self._project)
        list_instances = [Instance(self._api_client, instance) for instance in list_raw_instances]
        return list_instances
