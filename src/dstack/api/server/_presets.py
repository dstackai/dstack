from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.presets import PresetSpec
from dstack._internal.server.schemas.presets import (
    GetPresetFileRequest,
    GetPresetRequest,
    GetPresetResponse,
    PushPresetRequest,
    PushPresetResponse,
)
from dstack.api.server._group import APIClientGroup


class PresetsAPIClient(APIClientGroup):
    def push(self, project_name: str, name: str, spec: PresetSpec) -> PushPresetResponse:
        body = PushPresetRequest(name=name, spec=spec)
        resp = self._request(
            f"/api/project/{project_name}/presets/push", body=body.model_dump_json()
        )
        return validate_extra_ignore(PushPresetResponse, resp.json())

    def get(self, project_name: str, name_or_id: str) -> GetPresetResponse:
        body = GetPresetRequest(name_or_id=name_or_id)
        resp = self._request(
            f"/api/project/{project_name}/presets/get", body=body.model_dump_json()
        )
        return validate_extra_ignore(GetPresetResponse, resp.json())

    def get_file(self, project_name: str, name_or_id: str, path: str) -> bytes:
        body = GetPresetFileRequest(name_or_id=name_or_id, path=path)
        resp = self._request(
            f"/api/project/{project_name}/presets/get_file", body=body.model_dump_json()
        )
        return resp.content
