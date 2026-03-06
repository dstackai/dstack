import datetime
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, TypedDict, Union

from paramiko.pkey import PKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
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
from dstack._internal.server.services.fleets import get_fleet_spec
from dstack._internal.utils.common import UNSET, Unset, get_current_datetime
from dstack._internal.utils.ssh import pkey_from_str

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)
TERMINATION_RETRY_TIMEOUT = timedelta(seconds=30)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)
PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds


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


class HealthCheckCreate(TypedDict):
    instance_id: uuid.UUID
    collected_at: datetime.datetime
    status: HealthStatus
    response: str


@dataclass
class ProcessResult:
    instance_update_map: InstanceUpdateMap = field(default_factory=InstanceUpdateMap)
    health_check_create: Optional[HealthCheckCreate] = None
    new_placement_group_models: list[PlacementGroupModel] = field(default_factory=list)
    schedule_pg_deletion_fleet_id: Optional[uuid.UUID] = None
    schedule_pg_deletion_except_id: Optional[uuid.UUID] = None


async def can_terminate_fleet_instances_on_idle_duration(
    session: AsyncSession,
    fleet_model: FleetModel,
) -> bool:
    fleet_spec = get_fleet_spec(fleet_model)
    if fleet_spec.configuration.nodes is None or fleet_spec.autocreated:
        return True
    res = await session.execute(
        select(func.count(1)).where(
            InstanceModel.fleet_id == fleet_model.id,
            InstanceModel.deleted == False,
            InstanceModel.status.not_in(InstanceStatus.finished_statuses()),
        )
    )
    return res.scalar_one() > fleet_spec.configuration.nodes.min


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
    update_map: InstanceUpdateMap,
    instance_model: InstanceModel,
    new_status: InstanceStatus,
    termination_reason: Union[Optional[InstanceTerminationReason], Unset] = UNSET,
    termination_reason_message: Union[Optional[str], Unset] = UNSET,
) -> bool:
    old_status = instance_model.status
    changed = False
    if old_status == new_status:
        if not isinstance(termination_reason, Unset):
            update_map["termination_reason"] = termination_reason
            changed = True
        if not isinstance(termination_reason_message, Unset):
            update_map["termination_reason_message"] = termination_reason_message
            changed = True
        return changed

    effective_termination_reason = instance_model.termination_reason
    if not isinstance(termination_reason, Unset):
        effective_termination_reason = termination_reason
        update_map["termination_reason"] = effective_termination_reason
        changed = True

    effective_termination_reason_message = instance_model.termination_reason_message
    if not isinstance(termination_reason_message, Unset):
        effective_termination_reason_message = termination_reason_message
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
