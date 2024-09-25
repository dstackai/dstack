from typing import Optional
from uuid import UUID

from git import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.placement import (
    PlacementGroup,
    PlacementGroupConfiguration,
    PlacementGroupProvisioningData,
)
from dstack._internal.server.models import PlacementGroupModel


async def get_fleet_placement_groups(
    session: AsyncSession,
    fleet_id: UUID,
) -> List[PlacementGroup]:
    res = await session.execute(
        select(PlacementGroupModel).where(PlacementGroupModel.fleet_id == fleet_id)
    )
    placement_groups = res.scalars().all()
    return [placement_group_model_to_placement_group(pg) for pg in placement_groups]


def placement_group_model_to_placement_group(
    placement_group_model: PlacementGroupModel,
) -> PlacementGroup:
    configuration = get_placement_group_configuration(placement_group_model)
    provisioning_data = get_placement_group_provisioning_data(placement_group_model)
    return PlacementGroup(
        name=placement_group_model.name,
        project_name=placement_group_model.project.name,
        configuration=configuration,
        provisioning_data=provisioning_data,
    )


def get_placement_group_configuration(
    placement_group_model: PlacementGroupModel,
) -> PlacementGroupConfiguration:
    return PlacementGroupConfiguration.__response__.parse_raw(placement_group_model.configuration)


def get_placement_group_provisioning_data(
    placement_group_model: PlacementGroupModel,
) -> Optional[PlacementGroupProvisioningData]:
    if placement_group_model.provisioning_data is None:
        return None
    return PlacementGroupProvisioningData.__response__.parse_raw(
        placement_group_model.provisioning_data
    )
