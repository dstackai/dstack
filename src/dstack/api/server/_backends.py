from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.backends import (
    AnyConfigInfoWithCreds,
    AnyConfigInfoWithCredsPartial,
    AnyConfigValues,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.schemas.backends import DeleteBackendsRequest
from dstack.api.server._group import APIClientGroup


class BackendsAPIClient(APIClientGroup):
    def list_backend_types(self) -> List[BackendType]:
        resp = self._request("/api/backends/list_types")
        return parse_obj_as(List[BackendType], resp.json())

    def config_values(self, config: AnyConfigInfoWithCredsPartial) -> AnyConfigValues:
        resp = self._request("/api/backends/config_values", body=config.json())
        return parse_obj_as(AnyConfigValues, resp.json())

    def create(
        self, project_name: str, config: AnyConfigInfoWithCreds
    ) -> AnyConfigInfoWithCredsPartial:
        resp = self._request(f"/api/project/{project_name}/backends/create", body=config.json())
        return parse_obj_as(AnyConfigInfoWithCredsPartial, resp.json())

    def update(
        self, project_name: str, config: AnyConfigInfoWithCreds
    ) -> AnyConfigInfoWithCredsPartial:
        resp = self._request(f"/api/project/{project_name}/backends/update", body=config.json())
        return parse_obj_as(AnyConfigInfoWithCredsPartial, resp.json())

    def delete(self, project_name: str, backends_names: List[BackendType]):
        body = DeleteBackendsRequest(backends_names=backends_names)
        self._request(f"/api/project/{project_name}/backends/delete", body=body.json())

    def config_info(self, project_name: str, backend_name: BackendType) -> AnyConfigInfoWithCreds:
        resp = self._request(f"/api/project/{project_name}/backends/{backend_name}/config_info")
        return parse_obj_as(AnyConfigInfoWithCreds, resp.json())
