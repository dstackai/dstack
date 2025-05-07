from typing import Any, Dict, List, Optional, Union

from pydantic import parse_obj_as

from dstack._internal.core.models.fleets import ApplyFleetPlanInput, Fleet, FleetPlan, FleetSpec
from dstack._internal.core.models.instances import Instance
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
        body_json = body.json(exclude=_get_get_plan_excludes(spec))
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
        body_json = body.json(exclude=_get_apply_plan_excludes(plan_input))
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
        body_json = body.json(exclude=_get_create_fleet_excludes(spec))
        resp = self._request(f"/api/project/{project_name}/fleets/create", body=body_json)
        return parse_obj_as(Fleet.__response__, resp.json())


def _get_get_plan_excludes(fleet_spec: FleetSpec) -> Dict:
    get_plan_excludes = {}
    spec_excludes = _get_fleet_spec_excludes(fleet_spec)
    if spec_excludes:
        get_plan_excludes["spec"] = spec_excludes
    return get_plan_excludes


def _get_apply_plan_excludes(plan_input: ApplyFleetPlanInput) -> Dict:
    apply_plan_excludes = {}
    spec_excludes = _get_fleet_spec_excludes(plan_input.spec)
    if spec_excludes:
        apply_plan_excludes["spec"] = apply_plan_excludes
    current_resource = plan_input.current_resource
    if current_resource is not None:
        current_resource_excludes = {}
        apply_plan_excludes["current_resource"] = current_resource_excludes
        if all(map(_should_exclude_instance_cpu_arch, current_resource.instances)):
            current_resource_excludes["instances"] = {
                "__all__": {"instance_type": {"resources": {"cpu_arch"}}}
            }
    return {"plan": apply_plan_excludes}


def _should_exclude_instance_cpu_arch(instance: Instance) -> bool:
    try:
        return instance.instance_type.resources.cpu_arch is None
    except AttributeError:
        return True


def _get_create_fleet_excludes(fleet_spec: FleetSpec) -> Dict:
    create_fleet_excludes = {}
    spec_excludes = _get_fleet_spec_excludes(fleet_spec)
    if spec_excludes:
        create_fleet_excludes["spec"] = spec_excludes
    return create_fleet_excludes


def _get_fleet_spec_excludes(fleet_spec: FleetSpec) -> Optional[Dict]:
    """
    Returns `fleet_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: Dict[str, Any] = {}
    configuration_excludes: Dict[str, Any] = {}
    profile_excludes: set[str] = set()
    profile = fleet_spec.profile
    if profile.fleets is None:
        profile_excludes.add("fleets")
    if fleet_spec.configuration.tags is None:
        configuration_excludes["tags"] = True
    if profile.tags is None:
        profile_excludes.add("tags")
    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    if spec_excludes:
        return spec_excludes
    return None
