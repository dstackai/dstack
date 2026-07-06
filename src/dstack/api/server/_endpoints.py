from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.models.endpoints import Endpoint, EndpointConfiguration, EndpointPlan
from dstack._internal.server.schemas.endpoints import (
    CreateEndpointRequest,
    GetEndpointPlanRequest,
    GetEndpointRequest,
    StopEndpointsRequest,
)
from dstack.api.server._group import APIClientGroup


class EndpointsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Endpoint]:
        resp = self._request(f"/api/project/{project_name}/endpoints/list")
        return parse_obj_as(List[Endpoint.__response__], resp.json())

    def get(self, project_name: str, name: str) -> Endpoint:
        body = GetEndpointRequest(name=name)
        resp = self._request(f"/api/project/{project_name}/endpoints/get", body=body.json())
        return parse_obj_as(Endpoint.__response__, resp.json())

    def get_plan(
        self,
        project_name: str,
        configuration: EndpointConfiguration,
        configuration_path: str,
    ) -> EndpointPlan:
        body = GetEndpointPlanRequest(
            configuration=configuration,
            configuration_path=configuration_path,
        )
        resp = self._request(f"/api/project/{project_name}/endpoints/get_plan", body=body.json())
        return parse_obj_as(EndpointPlan.__response__, resp.json())

    def create(
        self,
        project_name: str,
        configuration: EndpointConfiguration,
    ) -> Endpoint:
        body = CreateEndpointRequest(configuration=configuration)
        resp = self._request(f"/api/project/{project_name}/endpoints/create", body=body.json())
        return parse_obj_as(Endpoint.__response__, resp.json())

    def stop(self, project_name: str, names: List[str]) -> None:
        body = StopEndpointsRequest(names=names)
        self._request(f"/api/project/{project_name}/endpoints/stop", body=body.json())
