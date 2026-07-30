from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.backends.models import (
    AnyBackendConfigWithCreds,
    AnyBackendConfigWithCredsTagged,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.server.schemas.backends import DeleteBackendsRequest
from dstack.api.server._group import APIClientGroup


class BackendsAPIClient(APIClientGroup):
    def list_backend_types(self) -> List[BackendType]:
        resp = self._request("/api/backends/list_types")
        backend_types = []
        for value in parse_obj_as(List[str], resp.json()):
            try:
                backend_types.append(BackendType(value))
            except ValueError:
                continue
        return backend_types

    def create(
        self, project_name: str, config: AnyBackendConfigWithCreds
    ) -> AnyBackendConfigWithCreds:
        resp = self._request(f"/api/project/{project_name}/backends/create", body=config.json())
        return validate_extra_ignore(AnyBackendConfigWithCredsTagged, resp.json())

    def update(
        self, project_name: str, config: AnyBackendConfigWithCreds
    ) -> AnyBackendConfigWithCreds:
        resp = self._request(f"/api/project/{project_name}/backends/update", body=config.json())
        return validate_extra_ignore(AnyBackendConfigWithCredsTagged, resp.json())

    def delete(self, project_name: str, backends_names: List[BackendType]):
        body = DeleteBackendsRequest(backends_names=backends_names)
        self._request(f"/api/project/{project_name}/backends/delete", body=body.json())

    def config_info(
        self, project_name: str, backend_name: BackendType
    ) -> AnyBackendConfigWithCreds:
        resp = self._request(f"/api/project/{project_name}/backends/{backend_name}/config_info")
        return validate_extra_ignore(AnyBackendConfigWithCredsTagged, resp.json())
