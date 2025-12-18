from collections.abc import Iterable
from typing import Optional
from uuid import UUID

from git import List
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import (
    ComputeWithPlacementGroupSupport,
    generate_unique_placement_group_name,
)
from dstack._internal.core.errors import BackendError, PlacementGroupNotSupportedError
from dstack._internal.core.models.instances import InstanceOffer
from dstack._internal.core.models.placement import (
    PlacementGroup,
    PlacementGroupConfiguration,
    PlacementGroupProvisioningData,
    PlacementStrategy,
)
from dstack._internal.server.models import FleetModel, InstanceModel, PlacementGroupModel
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


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


def placement_group_model_to_placement_group_optional(
    placement_group_model: Optional[PlacementGroupModel],
) -> Optional[PlacementGroup]:
    if placement_group_model is None:
        return None
    return placement_group_model_to_placement_group(placement_group_model)


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


async def get_fleet_placement_group_models(
    session: AsyncSession,
    fleet_id: Optional[UUID],
) -> List[PlacementGroupModel]:
    if fleet_id is None:
        return []
    res = await session.execute(
        select(PlacementGroupModel).where(
            and_(
                PlacementGroupModel.fleet_id == fleet_id,
                PlacementGroupModel.deleted == False,
                PlacementGroupModel.fleet_deleted == False,
            )
        )
    )
    return list(res.scalars().all())


async def schedule_fleet_placement_groups_deletion(
    session: AsyncSession, fleet_id: UUID, except_placement_group_ids: Iterable[UUID] = ()
):
    await session.execute(
        update(PlacementGroupModel)
        .where(
            and_(
                PlacementGroupModel.fleet_id == fleet_id,
                PlacementGroupModel.id.not_in(except_placement_group_ids),
            )
        )
        .values(fleet_deleted=True)  # TODO: rename `fleet_deleted` -> `to_be_deleted`
    )


def get_placement_group_model_for_instance(
    placement_group_models: list[PlacementGroupModel],
    instance_model: InstanceModel,
) -> Optional[PlacementGroupModel]:
    placement_group_model = None
    if not _is_fleet_master_instance(instance_model):
        if placement_group_models:
            placement_group_model = placement_group_models[0]
        if len(placement_group_models) > 1:
            logger.error(
                (
                    "Expected 0 or 1 placement groups associated with fleet %s, found %s."
                    " An incorrect placement group might have been selected for instance %s"
                ),
                instance_model.fleet_id,
                len(placement_group_models),
                instance_model.name,
            )
    return placement_group_model


def get_placement_group_model_for_job(
    placement_group_models: list[PlacementGroupModel],
    fleet_model: Optional[FleetModel],
) -> Optional[PlacementGroupModel]:
    """
    Returns any fleet placement group for jobs that provision
    in non-empty fleets and `None` for empty fleets.
    This is so that only the first job creates placement groups.
    """
    placement_group_model = None
    active_instances = []
    if fleet_model is not None:
        active_instances = [i for i in fleet_model.instances if not i.deleted]
    if len(active_instances) > 0 and len(placement_group_models) > 0:
        placement_group_model = placement_group_models[0]
    return placement_group_model


async def find_or_create_suitable_placement_group(
    fleet_model: FleetModel,
    placement_groups: List[PlacementGroupModel],
    instance_offer: InstanceOffer,
    compute: ComputeWithPlacementGroupSupport,
) -> Optional[PlacementGroupModel]:
    placement_group_model = find_suitable_placement_group(
        placement_groups=placement_groups,
        instance_offer=instance_offer,
        compute=compute,
    )
    if placement_group_model is None:
        placement_group_model = await create_placement_group(
            fleet_model=fleet_model,
            master_instance_offer=instance_offer,
            compute=compute,
        )
    return placement_group_model


def find_suitable_placement_group(
    placement_groups: List[PlacementGroupModel],
    instance_offer: InstanceOffer,
    compute: ComputeWithPlacementGroupSupport,
) -> Optional[PlacementGroupModel]:
    for pg in placement_groups:
        if compute.is_suitable_placement_group(
            placement_group_model_to_placement_group(pg), instance_offer
        ):
            return pg
    return None


async def create_placement_group(
    fleet_model: FleetModel,
    master_instance_offer: InstanceOffer,
    compute: ComputeWithPlacementGroupSupport,
) -> Optional[PlacementGroupModel]:
    placement_group_model = PlacementGroupModel(
        # TODO: generate the name in Compute.create_placement_group to allow
        # backend-specific name length limits
        name=generate_unique_placement_group_name(
            project_name=fleet_model.project.name,
            fleet_name=fleet_model.name,
        ),
        project=fleet_model.project,
        fleet=fleet_model,
        configuration=PlacementGroupConfiguration(
            backend=master_instance_offer.backend,
            region=master_instance_offer.region,
            placement_strategy=PlacementStrategy.CLUSTER,
        ).json(),
    )
    placement_group = placement_group_model_to_placement_group(placement_group_model)
    logger.debug(
        "Creating placement group %s in %s/%s",
        placement_group.name,
        placement_group.configuration.backend.value,
        placement_group.configuration.region,
    )
    try:
        pgpd = await run_async(
            compute.create_placement_group,
            placement_group_model_to_placement_group(placement_group_model),
            master_instance_offer,
        )
    except PlacementGroupNotSupportedError:
        logger.debug(
            "Skipping offer %s because placement group not supported",
            master_instance_offer.instance.name,
        )
        return None
    except BackendError as e:
        logger.warning(
            "Failed to create placement group %s in %s/%s: %r",
            placement_group.name,
            placement_group.configuration.backend.value,
            placement_group.configuration.region,
            e,
        )
        return None
    except Exception:
        logger.exception(
            "Got exception when creating placement group %s in %s/%s",
            placement_group.name,
            placement_group.configuration.backend.value,
            placement_group.configuration.region,
        )
        return None
    logger.info(
        "Created placement group %s in %s/%s",
        placement_group.name,
        placement_group.configuration.backend.value,
        placement_group.configuration.region,
    )
    placement_group_model.provisioning_data = pgpd.json()
    return placement_group_model


def _is_fleet_master_instance(instance: InstanceModel) -> bool:
    return instance.fleet is not None and instance.id == instance.fleet.instances[0].id
