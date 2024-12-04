from typing import List, Optional

from pydantic import parse_obj_as

from dstack._internal.core.models.fleets import Fleet, FleetPlan, FleetSpec
from dstack._internal.server.schemas.fleets import (
    CreateFleetRequest,
    DeleteFleetInstancesRequest,
    DeleteFleetsRequest,
    GetFleetPlanRequest,
    GetFleetRequest,
)
from dstack.api.server._group import APIClientGroup


class FleetsAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Fleet]:
        resp = self._request(f"/api/project/{project_name}/fleets/list")
        return parse_obj_as(List[Fleet.__response__], resp.json())

    def get(self, project_name: str, name: str) -> Fleet:
        body = GetFleetRequest(name=name)
        resp = self._request(f"/api/project/{project_name}/fleets/get", body=body.json())
        return parse_obj_as(Fleet.__response__, resp.json())

    def get_plan(
        self,
        project_name: str,
        spec: FleetSpec,
    ) -> FleetPlan:
        body = GetFleetPlanRequest(spec=spec)
        body_json = body.json(exclude=_get_fleet_spec_excludes(spec))
        resp = self._request(f"/api/project/{project_name}/fleets/get_plan", body=body_json)
        return parse_obj_as(FleetPlan.__response__, resp.json())

    def create(
        self,
        project_name: str,
        spec: FleetSpec,
    ) -> Fleet:
        body = CreateFleetRequest(spec=spec)
        body_json = body.json(exclude=_get_fleet_spec_excludes(spec))
        resp = self._request(f"/api/project/{project_name}/fleets/create", body=body_json)
        return parse_obj_as(Fleet.__response__, resp.json())

    def delete(self, project_name: str, names: List[str]) -> None:
        body = DeleteFleetsRequest(names=names)
        self._request(f"/api/project/{project_name}/fleets/delete", body=body.json())

    def delete_instances(self, project_name: str, name: str, instance_nums: List[int]) -> None:
        body = DeleteFleetInstancesRequest(name=name, instance_nums=instance_nums)
        self._request(f"/api/project/{project_name}/fleets/delete_instances", body=body.json())


def _get_fleet_spec_excludes(fleet_spec: FleetSpec) -> Optional[dict]:
    exclude = {}
    # TODO: Can be removed in 0.19
    if fleet_spec.configuration_path is None:
        exclude["spec"] = {"configuration_path"}
    if fleet_spec.configuration.ssh_config is not None:
        if all(
            isinstance(h, str) or h.internal_ip is None
            for h in fleet_spec.configuration.ssh_config.hosts
        ):
            exclude["spec"] = {
                "configuration": {"ssh_config": {"hosts": {"__all__": {"internal_ip"}}}}
            }
    return exclude or None
