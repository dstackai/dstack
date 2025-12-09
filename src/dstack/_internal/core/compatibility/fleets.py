from typing import Optional

from dstack._internal.core.models.common import IncludeExcludeDictType, IncludeExcludeSetType
from dstack._internal.core.models.fleets import ApplyFleetPlanInput, FleetSpec


def get_get_plan_excludes(fleet_spec: FleetSpec) -> IncludeExcludeDictType:
    get_plan_excludes: IncludeExcludeDictType = {}
    spec_excludes = get_fleet_spec_excludes(fleet_spec)
    if spec_excludes:
        get_plan_excludes["spec"] = spec_excludes
    return get_plan_excludes


def get_apply_plan_excludes(plan_input: ApplyFleetPlanInput) -> IncludeExcludeDictType:
    apply_plan_excludes: IncludeExcludeDictType = {}
    spec_excludes = get_fleet_spec_excludes(plan_input.spec)
    if spec_excludes:
        apply_plan_excludes["spec"] = spec_excludes
    current_resource = plan_input.current_resource
    if current_resource is not None:
        current_resource_excludes = {}
        apply_plan_excludes["current_resource"] = current_resource_excludes
    return {"plan": apply_plan_excludes}


def get_create_fleet_excludes(fleet_spec: FleetSpec) -> IncludeExcludeDictType:
    create_fleet_excludes: IncludeExcludeDictType = {}
    spec_excludes = get_fleet_spec_excludes(fleet_spec)
    if spec_excludes:
        create_fleet_excludes["spec"] = spec_excludes
    return create_fleet_excludes


def get_fleet_spec_excludes(fleet_spec: FleetSpec) -> Optional[IncludeExcludeDictType]:
    """
    Returns `fleet_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: IncludeExcludeDictType = {}
    configuration_excludes: IncludeExcludeDictType = {}
    profile_excludes: IncludeExcludeSetType = set()

    # Add excludes like this:
    #
    # if fleet_spec.configuration.tags is None:
    #     configuration_excludes["tags"] = True
    # if fleet_spec.profile.tags is None:
    #     profile_excludes.add("tags")

    if configuration_excludes:
        spec_excludes["configuration"] = configuration_excludes
    if profile_excludes:
        spec_excludes["profile"] = profile_excludes
    if spec_excludes:
        return spec_excludes
    return None
