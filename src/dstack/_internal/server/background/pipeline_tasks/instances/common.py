import datetime
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, TypedDict, Union, cast

from paramiko.pkey import PKey

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import InstanceGroupPlacement
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceTerminationReason,
    SSHKey,
)
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.background.pipeline_tasks.base import (
    ItemUpdateMap,
    UpdateMapDateTime,
)
from dstack._internal.server.background.scheduled_tasks.common import get_provisioning_timeout
from dstack._internal.server.models import FleetModel, InstanceModel, PlacementGroupModel
from dstack._internal.server.services.fleets import fleet_model_to_fleet, is_cloud_cluster
from dstack._internal.server.services.instances import (
    get_instance_provisioning_data,
    get_instance_status_change_message,
)
from dstack._internal.server.services.offers import get_instance_offer_with_restricted_az
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.ssh import pkey_from_str

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)
TERMINATION_RETRY_TIMEOUT = timedelta(seconds=30)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)
PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds

_UNSET = object()


class InstanceUpdateMap(ItemUpdateMap, total=False):
    status: InstanceStatus
    unreachable: bool
    started_at: UpdateMapDateTime
    finished_at: UpdateMapDateTime
    instance_configuration: str
    termination_deadline: Optional[datetime.datetime]
    termination_reason: Optional[InstanceTerminationReason]
    termination_reason_message: Optional[str]
    health: HealthStatus
    first_termination_retry_at: UpdateMapDateTime
    last_termination_retry_at: UpdateMapDateTime
    backend: BackendType
    backend_data: Optional[str]
    offer: str
    region: str
    price: float
    job_provisioning_data: str
    total_blocks: int
    busy_blocks: int
    deleted: bool
    deleted_at: UpdateMapDateTime


class SiblingInstanceUpdateMap(TypedDict, total=False):
    id: uuid.UUID
    status: InstanceStatus
    termination_reason: Optional[InstanceTerminationReason]
    termination_reason_message: Optional[str]


class HealthCheckCreate(TypedDict):
    instance_id: uuid.UUID
    collected_at: datetime.datetime
    status: HealthStatus
    response: str


@dataclass
class SiblingDeferredEvent:
    message: str
    project_id: uuid.UUID
    instance_id: uuid.UUID
    instance_name: str


@dataclass
class ProcessResult:
    instance_update_map: InstanceUpdateMap = field(default_factory=InstanceUpdateMap)
    sibling_update_rows: list[SiblingInstanceUpdateMap] = field(default_factory=list)
    sibling_deferred_events: list[SiblingDeferredEvent] = field(default_factory=list)
    health_check_create: Optional[HealthCheckCreate] = None
    new_placement_group_models: list[PlacementGroupModel] = field(default_factory=list)
    schedule_pg_deletion_fleet_id: Optional[uuid.UUID] = None
    schedule_pg_deletion_except_id: Optional[uuid.UUID] = None


def can_terminate_fleet_instances_on_idle_duration(fleet_model: FleetModel) -> bool:
    fleet = fleet_model_to_fleet(fleet_model)
    if fleet.spec.configuration.nodes is None or fleet.spec.autocreated:
        return True
    active_instances = [
        instance for instance in fleet_model.instances if instance.status.is_active()
    ]
    return len(active_instances) > fleet.spec.configuration.nodes.min


def get_fleet_master_instance(instance_model: InstanceModel) -> InstanceModel:
    if instance_model.fleet is None:
        return instance_model
    fleet_instances = list(instance_model.fleet.instances)
    if all(fleet_instance.id != instance_model.id for fleet_instance in fleet_instances):
        fleet_instances.append(instance_model)
    return min(
        fleet_instances,
        key=lambda fleet_instance: (fleet_instance.instance_num, fleet_instance.created_at),
    )


def need_to_wait_fleet_provisioning(
    instance_model: InstanceModel,
    master_instance_model: InstanceModel,
) -> bool:
    # Cluster cloud instances should wait for the first fleet instance to be provisioned
    # so that they are provisioned in the same backend/region.
    if instance_model.fleet is None:
        return False
    if (
        instance_model.id == master_instance_model.id
        or master_instance_model.job_provisioning_data is not None
        or master_instance_model.status == InstanceStatus.TERMINATED
    ):
        return False
    return is_cloud_cluster(instance_model.fleet)


def get_instance_offer_for_instance(
    instance_offer: InstanceOfferWithAvailability,
    instance_model: InstanceModel,
    master_instance_model: InstanceModel,
) -> InstanceOfferWithAvailability:
    if instance_model.fleet is None:
        return instance_offer
    fleet = fleet_model_to_fleet(instance_model.fleet)
    if fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER:
        master_job_provisioning_data = get_instance_provisioning_data(master_instance_model)
        return get_instance_offer_with_restricted_az(
            instance_offer=instance_offer,
            master_job_provisioning_data=master_job_provisioning_data,
        )
    return instance_offer


def get_instance_idle_duration(instance_model: InstanceModel) -> datetime.timedelta:
    last_time = instance_model.created_at
    if instance_model.last_job_processed_at is not None:
        last_time = instance_model.last_job_processed_at
    return get_current_datetime() - last_time


def get_provisioning_deadline(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
) -> datetime.datetime:
    assert instance_model.started_at is not None
    timeout_interval = get_provisioning_timeout(
        backend_type=job_provisioning_data.get_base_backend(),
        instance_type_name=job_provisioning_data.instance_type.name,
    )
    return instance_model.started_at + timeout_interval


def next_termination_retry_at(last_termination_retry_at: datetime.datetime) -> datetime.datetime:
    return last_termination_retry_at + TERMINATION_RETRY_TIMEOUT


def get_termination_deadline(first_termination_retry_at: datetime.datetime) -> datetime.datetime:
    return first_termination_retry_at + TERMINATION_RETRY_MAX_DURATION


def ssh_keys_to_pkeys(ssh_keys: list[SSHKey]) -> list[PKey]:
    return [pkey_from_str(ssh_key.private) for ssh_key in ssh_keys if ssh_key.private is not None]


def set_status_update(
    update_map: Union[InstanceUpdateMap, SiblingInstanceUpdateMap],
    instance_model: InstanceModel,
    new_status: InstanceStatus,
    termination_reason: object = _UNSET,
    termination_reason_message: object = _UNSET,
) -> bool:
    old_status = instance_model.status
    changed = False
    if old_status == new_status:
        if termination_reason is not _UNSET:
            update_map["termination_reason"] = cast(
                Optional[InstanceTerminationReason], termination_reason
            )
            changed = True
        if termination_reason_message is not _UNSET:
            update_map["termination_reason_message"] = cast(
                Optional[str], termination_reason_message
            )
            changed = True
        return changed

    effective_termination_reason = instance_model.termination_reason
    if termination_reason is not _UNSET:
        effective_termination_reason = cast(
            Optional[InstanceTerminationReason], termination_reason
        )
        update_map["termination_reason"] = effective_termination_reason
        changed = True

    effective_termination_reason_message = instance_model.termination_reason_message
    if termination_reason_message is not _UNSET:
        effective_termination_reason_message = cast(Optional[str], termination_reason_message)
        update_map["termination_reason_message"] = effective_termination_reason_message
        changed = True

    update_map["status"] = new_status
    changed = True
    return changed


def set_health_update(
    update_map: InstanceUpdateMap,
    instance_model: InstanceModel,
    health: HealthStatus,
) -> bool:
    if instance_model.health == health:
        return False
    update_map["health"] = health
    return True


def set_unreachable_update(
    update_map: InstanceUpdateMap,
    instance_model: InstanceModel,
    unreachable: bool,
) -> bool:
    if not instance_model.status.is_available() or instance_model.unreachable == unreachable:
        return False
    update_map["unreachable"] = unreachable
    return True


def append_sibling_status_event(
    deferred_events: list[SiblingDeferredEvent],
    instance_model: InstanceModel,
    new_status: InstanceStatus,
    termination_reason: Optional[InstanceTerminationReason],
    termination_reason_message: Optional[str],
) -> None:
    if instance_model.status == new_status:
        return
    deferred_events.append(
        SiblingDeferredEvent(
            message=get_instance_status_change_message(
                old_status=instance_model.status,
                new_status=new_status,
                termination_reason=termination_reason,
                termination_reason_message=termination_reason_message,
            ),
            project_id=instance_model.project_id,
            instance_id=instance_model.id,
            instance_name=instance_model.name,
        )
    )
