from typing import List

from pydantic import parse_obj_as

import dstack._internal.server.schemas.pool as pool_schemas
from dstack._internal.core.models.pool import Pool
from dstack.api.server._group import APIClientGroup


class PoolAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Pool]:
        resp = self._request(f"/api/project/{project_name}/pool/list")
        return parse_obj_as(List[Pool], resp.json())

    def delete(self, project_name: str, pool_name: str) -> None:
        body = pool_schemas.DeletePoolRequest(name=pool_name)
        self._request(f"/api/project/{project_name}/pool/delete", body=body.json())

    def create(self, project_name: str, pool_name: str) -> None:
        body = pool_schemas.CreatePoolRequest(name=pool_name)
        self._request(f"/api/project/{project_name}/pool/create", body=body.json())

    def show(self, project_name: str, pool_name: str) -> None:
        body = pool_schemas.ShowPoolRequest(name=pool_name)
        self._request(f"/api/project/{project_name}/pool/show", body=body.json())
