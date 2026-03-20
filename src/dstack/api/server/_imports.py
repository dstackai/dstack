from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.imports import Import
from dstack.api.server._group import APIClientGroup


class ImportsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Import]:
        resp = self._request(f"/api/project/{project_name}/imports/list")
        return parse_obj_as(List[Import.__response__], resp.json())
