import uuid
from dataclasses import dataclass
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.orm.attributes import set_committed_value

from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithPlacementGroupSupport,
    generate_unique_placement_group_name,
)
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT,
)
from dstack._internal.core.errors import (
    BackendError,
    PlacementGroupNotSupportedError,
)
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceTerminationReason,
)
from dstack._internal.core.models.placement import PlacementGroupConfiguration, PlacementStrategy
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    ProcessResult,
    set_status_update,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import FleetModel, InstanceModel, PlacementGroupModel
from dstack._internal.server.services.fleets import get_fleet_offers, is_cloud_cluster
from dstack._internal.server.services.instances import (
    get_instance_configuration,
    get_instance_profile,
    get_instance_provisioning_data,
    get_instance_requirements,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import get_instance_offer_with_restricted_az
from dstack._internal.server.services.placement import (
    get_fleet_placement_group_models,
    placement_group_model_to_placement_group,
    placement_group_model_to_placement_group_optional,
)
from dstack._internal.utils.common import get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _ClusterMasterContext:
    current_master_instance_model: InstanceModel
    is_current_instance_master: bool
    master_job_provisioning_data: Optional[JobProvisioningData]


async def create_cloud_instance(instance_model: InstanceModel) -> ProcessResult:
    result = ProcessResult()

    try:
        instance_configuration = get_instance_configuration(instance_model)
        profile = get_instance_profile(instance_model)
        requirements = get_instance_requirements(instance_model)
    except ValidationError as exc:
        logger.exception(
            "%s: error parsing profile, requirements or instance configuration",
            fmt(instance_model),
        )
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message=(
                f"Error to parse profile, requirements or instance_configuration: {exc}"
            ),
        )
        return result

    cluster_context = None
    placement_group_models: list[PlacementGroupModel] = []
    placement_group_model = None
    master_job_provisioning_data = None
    if instance_model.fleet is not None and is_cloud_cluster(instance_model.fleet):
        cluster_context = await _get_cluster_master_context(instance_model)
        if cluster_context is None:
            # Waiting for the master
            return result
        placement_group_models, placement_group_model = await _get_cluster_placement_context(
            instance_model=instance_model,
            cluster_context=cluster_context,
        )
        master_job_provisioning_data = cluster_context.master_job_provisioning_data

    offers = await get_fleet_offers(
        project=instance_model.project,
        profile=profile,
        requirements=requirements,
        fleet_model=instance_model.fleet,
        placement_group=placement_group_model_to_placement_group_optional(placement_group_model),
        blocks="auto" if instance_model.total_blocks is None else instance_model.total_blocks,
        exclude_not_available=True,
        master_job_provisioning_data=master_job_provisioning_data,
        infer_master_job_provisioning_data_from_fleet_instances=False,
        include_only_create_instance_supported_backends=True,
    )

    # Limit number of offers tried to prevent long-running processing in case all offers fail.
    for backend, instance_offer in offers[: server_settings.MAX_OFFERS_TRIED]:
        if instance_offer.backend not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT:
            continue
        compute = backend.compute()
        assert isinstance(compute, ComputeWithCreateInstanceSupport)
        if master_job_provisioning_data is not None:
            # `get_fleet_offers()` already restricts backend and region from the master.
            # Availability zone still has to be narrowed per offer.
            instance_offer = get_instance_offer_with_restricted_az(
                instance_offer=instance_offer,
                master_job_provisioning_data=master_job_provisioning_data,
            )
        if (
            cluster_context is not None
            and cluster_context.is_current_instance_master
            and instance_offer.backend in BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT
            and isinstance(compute, ComputeWithPlacementGroupSupport)
            and (
                compute.are_placement_groups_compatible_with_reservations(instance_offer.backend)
                or instance_configuration.reservation is None
            )
        ):
            (
                placement_group_model,
                created_placement_group_model,
            ) = await _find_or_create_suitable_placement_group_model(
                instance_model=instance_model,
                placement_group_models=placement_group_models,
                instance_offer=instance_offer,
                compute=compute,
            )
            if placement_group_model is None:
                continue
            if created_placement_group_model:
                placement_group_models.append(placement_group_model)
                result.new_placement_group_models.append(placement_group_model)

        logger.debug(
            "Trying %s in %s/%s for $%0.4f per hour",
            instance_offer.instance.name,
            instance_offer.backend.value,
            instance_offer.region,
            instance_offer.price,
        )
        try:
            job_provisioning_data = await run_async(
                compute.create_instance,
                instance_offer,
                instance_configuration,
                placement_group_model_to_placement_group_optional(placement_group_model),
            )
        except BackendError as exc:
            logger.warning(
                "%s launch in %s/%s failed: %s",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
                repr(exc),
                extra={"instance_name": instance_model.name},
            )
            continue
        except Exception:
            logger.exception(
                "Got exception when launching %s in %s/%s",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
            )
            continue

        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.PROVISIONING,
        )
        result.instance_update_map["backend"] = backend.TYPE
        result.instance_update_map["region"] = instance_offer.region
        result.instance_update_map["price"] = instance_offer.price
        result.instance_update_map["instance_configuration"] = instance_configuration.json()
        result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
        result.instance_update_map["offer"] = instance_offer.json()
        result.instance_update_map["total_blocks"] = instance_offer.total_blocks
        result.instance_update_map["started_at"] = NOW_PLACEHOLDER

        if (
            instance_model.fleet_id is not None
            and cluster_context is not None
            and cluster_context.is_current_instance_master
        ):
            # Clean up placement groups that did not end up being used.
            result.schedule_pg_deletion_fleet_id = instance_model.fleet_id
            if placement_group_model is not None:
                result.schedule_pg_deletion_except_id = placement_group_model.id
        return result

    set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATED,
        termination_reason=InstanceTerminationReason.NO_OFFERS,
        termination_reason_message="All offers failed" if offers else "No offers found",
    )
    return result


async def _get_cluster_master_context(
    instance_model: InstanceModel,
) -> Optional[_ClusterMasterContext]:
    assert instance_model.fleet is not None and is_cloud_cluster(instance_model.fleet)
    assert instance_model.fleet_id is not None
    async with get_session_ctx() as session:
        current_master_instance_model = await _load_current_master_instance(
            session=session,
            fleet_id=instance_model.fleet_id,
        )
    if current_master_instance_model is None:
        logger.debug(
            "%s: waiting for fleet pipeline to elect current cluster master",
            fmt(instance_model),
        )
        return None

    is_current_instance_master = current_master_instance_model.id == instance_model.id
    master_job_provisioning_data = None
    if not is_current_instance_master:
        if (
            current_master_instance_model.deleted
            or current_master_instance_model.status == InstanceStatus.TERMINATED
        ):
            logger.debug(
                "%s: waiting for fleet pipeline to replace current master %s",
                fmt(instance_model),
                current_master_instance_model.id,
            )
            return None
        master_job_provisioning_data = get_instance_provisioning_data(
            current_master_instance_model
        )
        if master_job_provisioning_data is None:
            logger.debug(
                "%s: waiting for current master %s to determine cluster placement",
                fmt(instance_model),
                current_master_instance_model.id,
            )
            return None

    return _ClusterMasterContext(
        current_master_instance_model=current_master_instance_model,
        is_current_instance_master=is_current_instance_master,
        master_job_provisioning_data=master_job_provisioning_data,
    )


async def _get_cluster_placement_context(
    instance_model: InstanceModel,
    cluster_context: _ClusterMasterContext,
) -> tuple[list[PlacementGroupModel], Optional[PlacementGroupModel]]:
    assert instance_model.fleet is not None and is_cloud_cluster(instance_model.fleet)
    assert instance_model.fleet_id is not None
    async with get_session_ctx() as session:
        placement_group_models = await get_fleet_placement_group_models(
            session=session,
            fleet_id=instance_model.fleet_id,
        )
    placement_group_model = None
    if not cluster_context.is_current_instance_master:
        # Non-master instances only reuse the placement group chosen by the
        # current master. They never create a new placement group themselves.
        placement_group_model = _get_current_master_placement_group_model(
            placement_group_models=placement_group_models,
            fleet_id=instance_model.fleet_id,
        )
        if placement_group_model is not None:
            _populate_current_master_placement_group_relations(
                placement_group_model=placement_group_model,
                instance_model=instance_model,
            )
    return placement_group_models, placement_group_model


async def _load_current_master_instance(
    session: AsyncSession,
    fleet_id: uuid.UUID,
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(FleetModel.current_master_instance_id).where(FleetModel.id == fleet_id)
    )
    current_master_instance_id = res.scalar_one_or_none()
    if current_master_instance_id is None:
        return None
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == current_master_instance_id,
        )
        .options(
            load_only(
                InstanceModel.id,
                InstanceModel.deleted,
                InstanceModel.status,
                InstanceModel.job_provisioning_data,
            )
        )
    )
    return res.scalar_one_or_none()


def _get_current_master_placement_group_model(
    placement_group_models: list[PlacementGroupModel],
    fleet_id: uuid.UUID,
) -> Optional[PlacementGroupModel]:
    if not placement_group_models:
        return None
    if len(placement_group_models) > 1:
        logger.error(
            "Expected 0 or 1 placement groups associated with fleet master %s, found %s."
            " Using the first placement group for this provisioning attempt.",
            fleet_id,
            len(placement_group_models),
        )
    return placement_group_models[0]


def _populate_current_master_placement_group_relations(
    placement_group_model: PlacementGroupModel,
    instance_model: InstanceModel,
) -> None:
    # Placement groups are loaded in a separate session from the instance worker.
    # Reattach the already-known project/fleet objects so later detached access
    # can still build a PlacementGroup value object without lazy loading.
    set_committed_value(placement_group_model, "project", instance_model.project)
    if instance_model.fleet is not None:
        set_committed_value(placement_group_model, "fleet", instance_model.fleet)


async def _find_or_create_suitable_placement_group_model(
    instance_model: InstanceModel,
    placement_group_models: list[PlacementGroupModel],
    instance_offer: InstanceOfferWithAvailability,
    compute: ComputeWithPlacementGroupSupport,
) -> tuple[Optional[PlacementGroupModel], bool]:
    for placement_group_model in placement_group_models:
        if compute.is_suitable_placement_group(
            placement_group_model_to_placement_group(placement_group_model),
            instance_offer,
        ):
            return placement_group_model, False

    assert instance_model.fleet is not None
    placement_group_id = uuid.uuid4()
    placement_group_name = generate_unique_placement_group_name(
        project_name=instance_model.project.name,
        fleet_name=instance_model.fleet.name,
    )
    placement_group_model = PlacementGroupModel(
        id=placement_group_id,
        name=placement_group_name,
        project=instance_model.project,
        fleet=get_or_error(instance_model.fleet),
        configuration=PlacementGroupConfiguration(
            backend=instance_offer.backend,
            region=instance_offer.region,
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
        provisioning_data = await run_async(
            compute.create_placement_group,
            placement_group,
            instance_offer,
        )
    except PlacementGroupNotSupportedError:
        logger.debug(
            "Skipping offer %s because placement group not supported",
            instance_offer.instance.name,
        )
        return None, False
    except BackendError as exc:
        logger.warning(
            "Failed to create placement group %s in %s/%s: %r",
            placement_group.name,
            placement_group.configuration.backend.value,
            placement_group.configuration.region,
            exc,
        )
        return None, False
    except Exception:
        logger.exception(
            "Got exception when creating placement group %s in %s/%s",
            placement_group.name,
            placement_group.configuration.backend.value,
            placement_group.configuration.region,
        )
        return None, False

    placement_group.provisioning_data = provisioning_data
    placement_group_model.provisioning_data = provisioning_data.json()
    return placement_group_model, True
