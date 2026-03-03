import uuid
from typing import Optional

from pydantic import ValidationError

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
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    ProcessResult,
    SiblingInstanceUpdateMap,
    append_sibling_status_event,
    get_fleet_master_instance,
    get_instance_offer_for_instance,
    need_to_wait_fleet_provisioning,
    set_status_update,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, PlacementGroupModel
from dstack._internal.server.services.fleets import get_create_instance_offers, is_cloud_cluster
from dstack._internal.server.services.instances import (
    get_instance_configuration,
    get_instance_profile,
    get_instance_requirements,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.placement import (
    get_fleet_placement_group_models,
    get_placement_group_model_for_instance,
    placement_group_model_to_placement_group,
    placement_group_model_to_placement_group_optional,
)
from dstack._internal.utils.common import get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def create_cloud_instance(instance_model: InstanceModel) -> ProcessResult:
    result = ProcessResult()
    master_instance_model = get_fleet_master_instance(instance_model)
    if need_to_wait_fleet_provisioning(instance_model, master_instance_model):
        logger.debug(
            "%s: waiting for the first instance in the fleet to be provisioned",
            fmt(instance_model),
        )
        return result

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

    # The placement group is determined when provisioning the master instance
    # and used for all other instances in the fleet.
    async with get_session_ctx() as session:
        placement_group_models = await get_fleet_placement_group_models(
            session=session,
            fleet_id=instance_model.fleet_id,
        )
    placement_group_model = get_placement_group_model_for_instance(
        placement_group_models=placement_group_models,
        instance_model=instance_model,
        master_instance_model=master_instance_model,
    )
    offers = await get_create_instance_offers(
        project=instance_model.project,
        profile=profile,
        requirements=requirements,
        fleet_model=instance_model.fleet,
        placement_group=placement_group_model_to_placement_group_optional(placement_group_model),
        blocks="auto" if instance_model.total_blocks is None else instance_model.total_blocks,
        exclude_not_available=True,
    )

    # Limit number of offers tried to prevent long-running processing in case all offers fail.
    for backend, instance_offer in offers[: server_settings.MAX_OFFERS_TRIED]:
        if instance_offer.backend not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT:
            continue
        compute = backend.compute()
        assert isinstance(compute, ComputeWithCreateInstanceSupport)
        instance_offer = get_instance_offer_for_instance(
            instance_offer=instance_offer,
            instance_model=instance_model,
            master_instance_model=master_instance_model,
        )
        if (
            instance_model.fleet is not None
            and is_cloud_cluster(instance_model.fleet)
            and instance_model.id == master_instance_model.id
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

        if instance_model.fleet_id is not None and instance_model.id == master_instance_model.id:
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
    if (
        instance_model.fleet is not None
        and instance_model.id == master_instance_model.id
        and is_cloud_cluster(instance_model.fleet)
    ):
        # Do not attempt to deploy other instances, as they won't determine the correct cluster
        # backend, region, and placement group without a successfully deployed master instance.
        for sibling_instance_model in instance_model.fleet.instances:
            if sibling_instance_model.id == instance_model.id:
                continue
            sibling_update_map = SiblingInstanceUpdateMap(id=sibling_instance_model.id)
            if set_status_update(
                update_map=sibling_update_map,
                instance_model=sibling_instance_model,
                new_status=InstanceStatus.TERMINATED,
                termination_reason=InstanceTerminationReason.MASTER_FAILED,
            ):
                result.sibling_update_rows.append(sibling_update_map)
                append_sibling_status_event(
                    deferred_events=result.sibling_deferred_events,
                    instance_model=sibling_instance_model,
                    new_status=InstanceStatus.TERMINATED,
                    termination_reason=sibling_update_map.get("termination_reason"),
                    termination_reason_message=sibling_update_map.get(
                        "termination_reason_message"
                    ),
                )
    return result


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
