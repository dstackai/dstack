from typing import List, Optional

from pydantic import parse_obj_as

import dstack._internal.server.schemas.pools as schemas_pools
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.server.schemas.runs import AddRemoteInstanceRequest
from dstack.api.server._group import APIClientGroup


class PoolAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Pool]:
        resp = self._request(f"/api/project/{project_name}/pool/list")
        return parse_obj_as(List[Pool], resp.json())

    def delete(self, project_name: str, pool_name: str, force: bool) -> None:
        body = schemas_pools.DeletePoolRequest(name=pool_name, force=force)
        self._request(f"/api/project/{project_name}/pool/delete", body=body.json())

    def create(self, project_name: str, pool_name: str) -> None:
        body = schemas_pools.CreatePoolRequest(name=pool_name)
        self._request(f"/api/project/{project_name}/pool/create", body=body.json())

    def show(self, project_name: str, pool_name: str) -> List[Instance]:
        body = schemas_pools.ShowPoolRequest(name=pool_name)
        resp = self._request(f"/api/project/{project_name}/pool/show", body=body.json())
        return parse_obj_as(List[Instance], resp.json())

    def add(
        self, project_name: str, pool_name: str, instance_name: Optional[str], host: str, port: str
    ):
        body = AddRemoteInstanceRequest(
            pool_name=pool_name, instance_name=instance_name, host=host, port=port
        )
        self._request(f"/api/project/{project_name}/pool/add", body=body.json())
