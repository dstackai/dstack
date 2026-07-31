from typing import List

from dstack._internal.core.compatibility.volumes import get_create_volume_excludes
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.volumes import AnyVolumeConfiguration, Volume
from dstack._internal.server.schemas.volumes import (
    CreateVolumeRequest,
    DeleteVolumesRequest,
    GetVolumeRequest,
)
from dstack.api.server._group import APIClientGroup


class VolumesAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Volume]:
        resp = self._request(f"/api/project/{project_name}/volumes/list")
        return validate_extra_ignore(List[Volume], resp.json())

    def get(self, project_name: str, name: str) -> Volume:
        body = GetVolumeRequest(name=name)
        resp = self._request(
            f"/api/project/{project_name}/volumes/get", body=body.model_dump_json()
        )
        return validate_extra_ignore(Volume, resp.json())

    def create(
        self,
        project_name: str,
        configuration: AnyVolumeConfiguration,
    ) -> Volume:
        body = CreateVolumeRequest(configuration=configuration)
        resp = self._request(
            f"/api/project/{project_name}/volumes/create",
            body=body.model_dump_json(exclude=get_create_volume_excludes(configuration)),
        )
        return validate_extra_ignore(Volume, resp.json())

    def delete(self, project_name: str, names: List[str]) -> None:
        body = DeleteVolumesRequest(names=names)
        self._request(f"/api/project/{project_name}/volumes/delete", body=body.model_dump_json())
