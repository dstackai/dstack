from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.endpoint_presets import EndpointPreset
from dstack._internal.server.schemas.endpoint_presets import DeleteEndpointPresetsRequest
from dstack.api.server._group import APIClientGroup


class EndpointPresetsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[EndpointPreset]:
        resp = self._request(f"/api/project/{project_name}/endpoints/presets/list")
        return parse_obj_as(List[EndpointPreset.__response__], resp.json())

    def delete(self, project_name: str, names: List[str]) -> None:
        body = DeleteEndpointPresetsRequest(names=names)
        self._request(
            f"/api/project/{project_name}/endpoints/presets/delete",
            body=body.json(),
        )
