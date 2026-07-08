from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.endpoint_presets import EndpointPreset
from dstack._internal.server.schemas.endpoint_presets import (
    DeleteEndpointPresetsRequest,
    GetEndpointPresetRequest,
)
from dstack.api.server._group import APIClientGroup


class EndpointPresetsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[EndpointPreset]:
        resp = self._request(f"/api/project/{project_name}/endpoints/presets/list")
        return parse_obj_as(List[EndpointPreset.__response__], resp.json())

    def get(self, project_name: str, model: str) -> EndpointPreset:
        body = GetEndpointPresetRequest(model=model)
        resp = self._request(
            f"/api/project/{project_name}/endpoints/presets/get",
            body=body.json(),
        )
        return parse_obj_as(EndpointPreset.__response__, resp.json())

    def delete(self, project_name: str, models: List[str]) -> None:
        body = DeleteEndpointPresetsRequest(models=models)
        self._request(
            f"/api/project/{project_name}/endpoints/presets/delete",
            body=body.json(),
        )
