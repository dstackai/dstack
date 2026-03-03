import uuid
from dataclasses import dataclass
from typing import Optional, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import joinedload

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
from dstack._internal.core.models.placement import (
    PlacementGroup,
    PlacementGroupConfiguration,
    PlacementStrategy,
)
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    PlacementGroupCreate,
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
from dstack._internal.server.services.placement import placement_group_model_to_placement_group
from dstack._internal.utils.common import get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _PlacementGroupState:
    id: uuid.UUID
    placement_group: PlacementGroup
    create_payload: Optional[PlacementGroupCreate] = None


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

    placement_group_states = await _get_fleet_placement_group_states(instance_model.fleet_id)
    placement_group_state = _get_placement_group_state_for_instance(
        placement_group_states=placement_group_states,
        instance_model=instance_model,
        master_instance_model=master_instance_model,
    )
    offers = await get_create_instance_offers(
        project=instance_model.project,
        profile=profile,
        requirements=requirements,
        fleet_model=instance_model.fleet,
        placement_group=(
            placement_group_state.placement_group if placement_group_state is not None else None
        ),
        blocks="auto" if instance_model.total_blocks is None else instance_model.total_blocks,
        exclude_not_available=True,
    )

    seen_placement_group_ids = {state.id for state in placement_group_states}
    for backend, instance_offer in offers[: server_settings.MAX_OFFERS_TRIED]:
        if instance_offer.backend not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT:
            continue
        compute = backend.compute()
        assert isinstance(compute, ComputeWithCreateInstanceSupport)
        selected_offer = get_instance_offer_for_instance(
            instance_offer=instance_offer,
            instance_model=instance_model,
            master_instance_model=master_instance_model,
        )
        selected_placement_group_state = placement_group_state
        if (
            instance_model.fleet is not None
            and is_cloud_cluster(instance_model.fleet)
            and instance_model.id == master_instance_model.id
            and selected_offer.backend in BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT
            and isinstance(compute, ComputeWithPlacementGroupSupport)
            and (
                compute.are_placement_groups_compatible_with_reservations(selected_offer.backend)
                or instance_configuration.reservation is None
            )
        ):
            selected_placement_group_state = await _find_or_create_suitable_placement_group_state(
                instance_model=instance_model,
                placement_group_states=placement_group_states,
                instance_offer=selected_offer,
                compute=compute,
            )
            if selected_placement_group_state is None:
                continue
            if (
                selected_placement_group_state.create_payload is not None
                and selected_placement_group_state.id not in seen_placement_group_ids
            ):
                seen_placement_group_ids.add(selected_placement_group_state.id)
                placement_group_states.append(selected_placement_group_state)
                result.placement_group_creates.append(
                    selected_placement_group_state.create_payload
                )

        logger.debug(
            "Trying %s in %s/%s for $%0.4f per hour",
            selected_offer.instance.name,
            selected_offer.backend.value,
            selected_offer.region,
            selected_offer.price,
        )
        try:
            job_provisioning_data = await run_async(
                compute.create_instance,
                selected_offer,
                instance_configuration,
                selected_placement_group_state.placement_group
                if selected_placement_group_state is not None
                else None,
            )
        except BackendError as exc:
            logger.warning(
                "%s launch in %s/%s failed: %s",
                selected_offer.instance.name,
                selected_offer.backend.value,
                selected_offer.region,
                repr(exc),
                extra={"instance_name": instance_model.name},
            )
            continue
        except Exception:
            logger.exception(
                "Got exception when launching %s in %s/%s",
                selected_offer.instance.name,
                selected_offer.backend.value,
                selected_offer.region,
            )
            continue

        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.PROVISIONING,
        )
        result.instance_update_map["backend"] = backend.TYPE
        result.instance_update_map["region"] = selected_offer.region
        result.instance_update_map["price"] = selected_offer.price
        result.instance_update_map["instance_configuration"] = instance_configuration.json()
        result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
        result.instance_update_map["offer"] = selected_offer.json()
        result.instance_update_map["total_blocks"] = selected_offer.total_blocks
        result.instance_update_map["started_at"] = NOW_PLACEHOLDER

        if instance_model.fleet_id is not None and instance_model.id == master_instance_model.id:
            result.schedule_pg_deletion_fleet_id = instance_model.fleet_id
            if selected_placement_group_state is not None:
                result.schedule_pg_deletion_except_ids = (selected_placement_group_state.id,)
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
        for sibling_instance_model in instance_model.fleet.instances:
            if sibling_instance_model.id == instance_model.id:
                continue
            sibling_update_map = SiblingInstanceUpdateMap(id=sibling_instance_model.id)
            set_status_update(
                update_map=sibling_update_map,
                instance_model=sibling_instance_model,
                new_status=InstanceStatus.TERMINATED,
                termination_reason=InstanceTerminationReason.MASTER_FAILED,
            )
            if len(sibling_update_map) > 1:
                result.sibling_update_rows.append(sibling_update_map)
                append_sibling_status_event(
                    deferred_events=result.sibling_deferred_events,
                    instance_model=sibling_instance_model,
                    new_status=InstanceStatus.TERMINATED,
                    termination_reason=cast(
                        Optional[InstanceTerminationReason],
                        sibling_update_map.get("termination_reason"),
                    ),
                    termination_reason_message=cast(
                        Optional[str], sibling_update_map.get("termination_reason_message")
                    ),
                )
    return result


async def _get_fleet_placement_group_states(
    fleet_id: Optional[uuid.UUID],
) -> list[_PlacementGroupState]:
    if fleet_id is None:
        return []
    async with get_session_ctx() as session:
        res = await session.execute(
            select(PlacementGroupModel)
            .where(
                PlacementGroupModel.fleet_id == fleet_id,
                PlacementGroupModel.deleted == False,
                PlacementGroupModel.fleet_deleted == False,
            )
            .options(joinedload(PlacementGroupModel.project))
        )
        placement_group_models = list(res.unique().scalars().all())
    return [
        _PlacementGroupState(
            id=placement_group_model.id,
            placement_group=placement_group_model_to_placement_group(placement_group_model),
        )
        for placement_group_model in placement_group_models
    ]


def _get_placement_group_state_for_instance(
    placement_group_states: list[_PlacementGroupState],
    instance_model: InstanceModel,
    master_instance_model: InstanceModel,
) -> Optional[_PlacementGroupState]:
    if instance_model.id == master_instance_model.id:
        return None
    if len(placement_group_states) > 1:
        logger.error(
            (
                "Expected 0 or 1 placement groups associated with fleet %s, found %s."
                " An incorrect placement group might have been selected for instance %s"
            ),
            instance_model.fleet_id,
            len(placement_group_states),
            instance_model.name,
        )
    if placement_group_states:
        return placement_group_states[0]
    return None


async def _find_or_create_suitable_placement_group_state(
    instance_model: InstanceModel,
    placement_group_states: list[_PlacementGroupState],
    instance_offer: InstanceOfferWithAvailability,
    compute: ComputeWithPlacementGroupSupport,
) -> Optional[_PlacementGroupState]:
    for placement_group_state in placement_group_states:
        if compute.is_suitable_placement_group(
            placement_group_state.placement_group,
            instance_offer,
        ):
            return placement_group_state

    assert instance_model.fleet is not None
    placement_group_id = uuid.uuid4()
    placement_group_name = generate_unique_placement_group_name(
        project_name=instance_model.project.name,
        fleet_name=instance_model.fleet.name,
    )
    placement_group = PlacementGroup(
        name=placement_group_name,
        project_name=instance_model.project.name,
        configuration=PlacementGroupConfiguration(
            backend=instance_offer.backend,
            region=instance_offer.region,
            placement_strategy=PlacementStrategy.CLUSTER,
        ),
        provisioning_data=None,
    )
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
        return None
    except BackendError as exc:
        logger.warning(
            "Failed to create placement group %s in %s/%s: %r",
            placement_group.name,
            placement_group.configuration.backend.value,
            placement_group.configuration.region,
            exc,
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

    placement_group.provisioning_data = provisioning_data
    return _PlacementGroupState(
        id=placement_group_id,
        placement_group=placement_group,
        create_payload=PlacementGroupCreate(
            id=placement_group_id,
            name=placement_group.name,
            project_id=instance_model.project_id,
            fleet_id=get_or_error(instance_model.fleet_id),
            configuration=placement_group.configuration.json(),
            provisioning_data=provisioning_data.json(),
        ),
    )
