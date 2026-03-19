from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.fleets import Fleet, FleetPlan, FleetSpec
from dstack._internal.server.compatibility.common import patch_offers_list, patch_profile_params


def patch_fleet_plan(fleet_plan: FleetPlan, client_version: Optional[Version]) -> None:
    patch_fleet_spec(fleet_plan.spec, client_version)
    if fleet_plan.effective_spec is not None:
        patch_fleet_spec(fleet_plan.effective_spec, client_version)
    if fleet_plan.current_resource is not None:
        patch_fleet(fleet_plan.current_resource, client_version)
    patch_offers_list(fleet_plan.offers, client_version)


def patch_fleet(fleet: Fleet, client_version: Optional[Version]) -> None:
    patch_fleet_spec(fleet.spec, client_version)


def patch_fleet_spec(fleet_spec: FleetSpec, client_version: Optional[Version]) -> None:
    patch_profile_params(fleet_spec.profile, client_version)
