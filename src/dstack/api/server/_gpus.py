from typing import List, Optional

from pydantic import parse_obj_as

from dstack._internal.core.compatibility.gpus import get_list_gpus_excludes
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.schemas.gpus import GpuGroup, ListGpusRequest, ListGpusResponse
from dstack.api.server._group import APIClientGroup


class GpusAPIClient(APIClientGroup):
    def list_gpus(
        self,
        project_name: str,
        run_spec: RunSpec,
        group_by: Optional[List[str]] = None,
    ) -> List[GpuGroup]:
        body = ListGpusRequest(run_spec=run_spec, group_by=group_by)
        resp = self._request(
            f"/api/project/{project_name}/gpus/list",
            body=body.json(exclude=get_list_gpus_excludes(body)),
        )
        return parse_obj_as(ListGpusResponse, resp.json()).gpus
