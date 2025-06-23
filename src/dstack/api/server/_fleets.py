from typing import List, Union

from pydantic import parse_obj_as

from dstack._internal.core.compatibility.fleets import (
    get_apply_plan_excludes,
    get_create_fleet_excludes,
    get_get_plan_excludes,
)
from dstack._internal.core.models.fleets import ApplyFleetPlanInput, Fleet, FleetPlan, FleetSpec
from dstack._internal.server.schemas.fleets import (
    ApplyFleetPlanRequest,
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
        resp = self._request(
            f"/api/project/{project_name}/fleets/get",
            body=body.json(),
        )
        return parse_obj_as(Fleet.__response__, resp.json())

    def get_plan(
        self,
        project_name: str,
        spec: FleetSpec,
    ) -> FleetPlan:
        body = GetFleetPlanRequest(spec=spec)
        body_json = body.json(exclude=get_get_plan_excludes(spec))
        resp = self._request(f"/api/project/{project_name}/fleets/get_plan", body=body_json)
        return parse_obj_as(FleetPlan.__response__, resp.json())

    def apply_plan(
        self,
        project_name: str,
        plan: Union[FleetPlan, ApplyFleetPlanInput],
        force: bool = False,
    ) -> Fleet:
        plan_input = ApplyFleetPlanInput.__response__.parse_obj(plan)
        body = ApplyFleetPlanRequest(plan=plan_input, force=force)
        body_json = body.json(exclude=get_apply_plan_excludes(plan_input))
        resp = self._request(f"/api/project/{project_name}/fleets/apply", body=body_json)
        return parse_obj_as(Fleet.__response__, resp.json())

    def delete(self, project_name: str, names: List[str]) -> None:
        body = DeleteFleetsRequest(names=names)
        self._request(f"/api/project/{project_name}/fleets/delete", body=body.json())

    def delete_instances(self, project_name: str, name: str, instance_nums: List[int]) -> None:
        body = DeleteFleetInstancesRequest(name=name, instance_nums=instance_nums)
        self._request(f"/api/project/{project_name}/fleets/delete_instances", body=body.json())

    # Deprecated
    # TODO: Remove in 0.20
    def create(
        self,
        project_name: str,
        spec: FleetSpec,
    ) -> Fleet:
        body = CreateFleetRequest(spec=spec)
        body_json = body.json(exclude=get_create_fleet_excludes(spec))
        resp = self._request(f"/api/project/{project_name}/fleets/create", body=body_json)
        return parse_obj_as(Fleet.__response__, resp.json())
