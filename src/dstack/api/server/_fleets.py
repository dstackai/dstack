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
    # Handle old server versions that do not accept configuration_path
    # TODO: Can be removed in 0.19
    if fleet_spec.configuration_path is None:
        exclude = {"spec": {"configuration_path"}}

    # client >= 0.18.26 / server <= 0.18.25 compatibility tweak
    if not fleet_spec.configuration.reservation:
        exclude.setdefault("spec", {})
        exclude["spec"].setdefault("configuration", set())
        exclude["spec"]["configuration"].add("reservation")
        exclude["spec"].setdefault("profile", set())
        exclude["spec"]["profile"].add("reservation")

    return exclude or None
