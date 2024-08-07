from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.volumes import Volume, VolumeConfiguration
from dstack._internal.server.schemas.volumes import (
    CreateVolumeRequest,
    DeleteVolumesRequest,
    GetVolumeRequest,
)
from dstack.api.server._group import APIClientGroup


class VolumesAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Volume]:
        resp = self._request(f"/api/project/{project_name}/volumes/list")
        return parse_obj_as(List[Volume.__response__], resp.json())

    def get(self, project_name: str, name: str) -> Volume:
        body = GetVolumeRequest(name=name)
        resp = self._request(f"/api/project/{project_name}/volumes/get", body=body.json())
        return parse_obj_as(Volume.__response__, resp.json())

    def create(
        self,
        project_name: str,
        configuration: VolumeConfiguration,
    ) -> Volume:
        body = CreateVolumeRequest(configuration=configuration)
        resp = self._request(f"/api/project/{project_name}/volumes/create", body=body.json())
        return parse_obj_as(Volume.__response__, resp.json())

    def delete(self, project_name: str, names: List[str]) -> None:
        body = DeleteVolumesRequest(names=names)
        self._request(f"/api/project/{project_name}/volumes/delete", body=body.json())
