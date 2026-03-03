import asyncio
import datetime
import logging
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, Optional, Sequence, TypedDict, Union, cast

import gpuhunt
import requests
from paramiko.pkey import PKey
from paramiko.ssh_exception import PasswordRequiredException
from pydantic import ValidationError
from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from dstack._internal import settings
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithPlacementGroupSupport,
    GoArchType,
    generate_unique_placement_group_name,
    get_dstack_runner_binary_path,
    get_dstack_runner_download_url,
    get_dstack_runner_version,
    get_dstack_shim_binary_path,
    get_dstack_shim_download_url,
    get_dstack_shim_version,
    get_dstack_working_dir,
    get_shim_env,
    get_shim_pre_start_commands,
)
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT,
)
from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import (
    BackendError,
    NotYetTerminated,
    PlacementGroupNotSupportedError,
    ProvisioningError,
    SSHProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.events import EventTargetType
from dstack._internal.core.models.fleets import InstanceGroupPlacement
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceStatus,
    InstanceTerminationReason,
    RemoteConnectionInfo,
    SSHKey,
)
from dstack._internal.core.models.placement import (
    PlacementGroup,
    PlacementGroupConfiguration,
    PlacementStrategy,
)
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.base import (
    NOW_PLACEHOLDER,
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    UpdateMapDateTime,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.background.scheduled_tasks.common import get_provisioning_timeout
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceHealthCheckModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    ProjectModel,
)
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import (
    ComponentInfo,
    ComponentStatus,
    HealthcheckResponse,
    InstanceHealthResponse,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events
from dstack._internal.server.services.fleets import (
    fleet_model_to_fleet,
    get_create_instance_offers,
    is_cloud_cluster,
)
from dstack._internal.server.services.instances import (
    emit_instance_status_change_event,
    get_instance_configuration,
    get_instance_profile,
    get_instance_provisioning_data,
    get_instance_remote_connection_info,
    get_instance_requirements,
    get_instance_ssh_private_keys,
    get_instance_status_change_message,
    is_ssh_instance,
    remove_dangling_tasks_from_instance,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import (
    get_instance_offer_with_restricted_az,
    is_divisible_into_blocks,
)
from dstack._internal.server.services.placement import (
    placement_group_model_to_placement_group,
    schedule_fleet_placement_groups_deletion,
)
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.ssh_fleets.provisioning import (
    detect_cpu_arch,
    get_host_info,
    get_paramiko_connection,
    get_shim_healthcheck,
    host_info_to_instance_type,
    remove_dstack_runner_if_exists,
    remove_host_info_if_exists,
    run_pre_start_commands,
    run_shim_as_systemd_service,
    upload_envs,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.network import get_ip_from_network, is_ip_among_addresses
from dstack._internal.utils.ssh import pkey_from_str

logger = get_logger(__name__)

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)
TERMINATION_RETRY_TIMEOUT = timedelta(seconds=30)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)
PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds

_UNSET = object()


@dataclass
class InstancePipelineItem(PipelineItem):
    status: InstanceStatus


class InstancePipeline(Pipeline[InstancePipelineItem]):
    def __init__(
        self,
        workers_num: int = 10,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=10),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[InstancePipelineItem](
            model_type=InstanceModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = InstanceFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            InstanceWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return InstanceModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[InstancePipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[InstancePipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["InstanceWorker"]:
        return self.__workers


class InstanceFetcher(Fetcher[InstancePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[InstancePipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[InstancePipelineItem],
        queue_check_delay: float = 1.0,
    ) -> None:
        super().__init__(
            queue=queue,
            queue_desired_minsize=queue_desired_minsize,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeater=heartbeater,
            queue_check_delay=queue_check_delay,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.InstanceFetcher.fetch")
    async def fetch(self, limit: int) -> list[InstancePipelineItem]:
        instance_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            InstanceModel.__tablename__
        )
        async with instance_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(InstanceModel)
                    .where(
                        InstanceModel.status.in_(
                            [
                                InstanceStatus.PENDING,
                                InstanceStatus.PROVISIONING,
                                InstanceStatus.BUSY,
                                InstanceStatus.IDLE,
                                InstanceStatus.TERMINATING,
                            ]
                        ),
                        not_(
                            and_(
                                InstanceModel.status == InstanceStatus.TERMINATING,
                                InstanceModel.compute_group_id.is_not(None),
                            )
                        ),
                        InstanceModel.deleted == False,
                        InstanceModel.last_processed_at <= now - self._min_processing_interval,
                        or_(
                            InstanceModel.lock_expires_at.is_(None),
                            InstanceModel.lock_expires_at < now,
                        ),
                        or_(
                            InstanceModel.lock_owner.is_(None),
                            InstanceModel.lock_owner == InstancePipeline.__name__,
                        ),
                    )
                    .order_by(InstanceModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=InstanceModel)
                    .options(
                        load_only(
                            InstanceModel.id,
                            InstanceModel.lock_token,
                            InstanceModel.lock_expires_at,
                            InstanceModel.status,
                        )
                    )
                )
                instance_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for instance_model in instance_models:
                    prev_lock_expired = instance_model.lock_expires_at is not None
                    instance_model.lock_expires_at = lock_expires_at
                    instance_model.lock_token = lock_token
                    instance_model.lock_owner = InstancePipeline.__name__
                    items.append(
                        InstancePipelineItem(
                            __tablename__=InstanceModel.__tablename__,
                            id=instance_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=instance_model.status,
                        )
                    )
                await session.commit()
        return items


class InstanceWorker(Worker[InstancePipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[InstancePipelineItem],
        heartbeater: Heartbeater[InstancePipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.InstanceWorker.process")
    async def process(self, item: InstancePipelineItem):
        async with get_session_ctx() as session:
            instance_model = await _refetch_locked_instance_status(session=session, item=item)
            if instance_model is None:
                log_lock_token_mismatch(logger, item)
                return
            status = instance_model.status

        result: Optional[_ProcessResult] = None
        if status == InstanceStatus.PENDING:
            result = await _process_pending_item(item)
        elif status == InstanceStatus.PROVISIONING:
            result = await _process_provisioning_item(item)
        elif status == InstanceStatus.IDLE:
            result = await _process_idle_item(item)
        elif status == InstanceStatus.BUSY:
            result = await _process_busy_item(item)
        elif status == InstanceStatus.TERMINATING:
            result = await _process_terminating_item(item)
        if result is None:
            # FIXME: Item won't be unlocked!!!
            return
        set_processed_update_map_fields(result.instance_update_map)
        set_unlock_update_map_fields(result.instance_update_map)
        await _apply_process_result(item=item, result=result)


class _InstanceUpdateMap(ItemUpdateMap, total=False):
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


class _SiblingInstanceUpdateMap(TypedDict, total=False):
    id: uuid.UUID
    status: InstanceStatus
    termination_reason: Optional[InstanceTerminationReason]
    termination_reason_message: Optional[str]


class _HealthCheckCreate(TypedDict):
    instance_id: uuid.UUID
    collected_at: datetime.datetime
    status: HealthStatus
    response: str


class _PlacementGroupCreate(TypedDict):
    id: uuid.UUID
    name: str
    project_id: uuid.UUID
    fleet_id: uuid.UUID
    configuration: str
    provisioning_data: str


@dataclass
class _SiblingDeferredEvent:
    message: str
    project_id: uuid.UUID
    instance_id: uuid.UUID
    instance_name: str


@dataclass
class _PlacementGroupState:
    id: uuid.UUID
    placement_group: PlacementGroup
    create_payload: Optional[_PlacementGroupCreate] = None


@dataclass
class _ProcessResult:
    instance_update_map: _InstanceUpdateMap = field(default_factory=_InstanceUpdateMap)
    sibling_update_rows: list[_SiblingInstanceUpdateMap] = field(default_factory=list)
    sibling_deferred_events: list[_SiblingDeferredEvent] = field(default_factory=list)
    health_check_create: Optional[_HealthCheckCreate] = None
    placement_group_creates: list[_PlacementGroupCreate] = field(default_factory=list)
    schedule_pg_deletion_fleet_id: Optional[uuid.UUID] = None
    schedule_pg_deletion_except_ids: tuple[uuid.UUID, ...] = ()


async def _process_pending_item(item: InstancePipelineItem) -> Optional[_ProcessResult]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_pending_or_terminating(
            session=session,
            item=item,
        )
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    if is_ssh_instance(instance_model):
        return await _add_ssh_instance(instance_model)
    return await _create_cloud_instance(instance_model)


async def _process_provisioning_item(item: InstancePipelineItem) -> Optional[_ProcessResult]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_check(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    return await _check_instance(instance_model)


async def _process_idle_item(item: InstancePipelineItem) -> Optional[_ProcessResult]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_idle(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    idle_result = _process_idle_timeout(instance_model)
    if idle_result is not None:
        return idle_result
    return await _check_instance(instance_model)


async def _process_busy_item(item: InstancePipelineItem) -> Optional[_ProcessResult]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_check(session=session, item=item)
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    return await _check_instance(instance_model)


async def _process_terminating_item(item: InstancePipelineItem) -> Optional[_ProcessResult]:
    async with get_session_ctx() as session:
        instance_model = await _refetch_locked_instance_for_pending_or_terminating(
            session=session,
            item=item,
        )
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return None
    return await _terminate_instance(instance_model)


async def _refetch_locked_instance_status(
    session: AsyncSession,
    item: InstancePipelineItem,
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(load_only(InstanceModel.id, InstanceModel.status))
    )
    return res.scalar_one_or_none()


async def _refetch_locked_instance_for_pending_or_terminating(
    session: AsyncSession,
    item: InstancePipelineItem,
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(joinedload(InstanceModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
        .options(
            joinedload(InstanceModel.fleet).joinedload(FleetModel.project),
        )
        .options(
            joinedload(InstanceModel.fleet)
            .joinedload(FleetModel.instances.and_(InstanceModel.deleted == False))
            .joinedload(InstanceModel.project)
        )
        .options(
            joinedload(InstanceModel.fleet)
            .joinedload(FleetModel.instances.and_(InstanceModel.deleted == False))
            .joinedload(InstanceModel.fleet)
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _refetch_locked_instance_for_idle(
    session: AsyncSession,
    item: InstancePipelineItem,
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(joinedload(InstanceModel.project))
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
        .options(
            joinedload(InstanceModel.fleet).joinedload(
                FleetModel.instances.and_(InstanceModel.deleted == False)
            )
        )
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _refetch_locked_instance_for_check(
    session: AsyncSession,
    item: InstancePipelineItem,
) -> Optional[InstanceModel]:
    res = await session.execute(
        select(InstanceModel)
        .where(
            InstanceModel.id == item.id,
            InstanceModel.lock_token == item.lock_token,
        )
        .options(joinedload(InstanceModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


def _process_idle_timeout(instance_model: InstanceModel) -> Optional[_ProcessResult]:
    if not (
        instance_model.status == InstanceStatus.IDLE
        and instance_model.termination_policy == TerminationPolicy.DESTROY_AFTER_IDLE
        and not instance_model.jobs
    ):
        return None
    if instance_model.fleet is not None and not _can_terminate_fleet_instances_on_idle_duration(
        instance_model.fleet
    ):
        logger.debug(
            "Skipping instance %s termination on idle duration. Fleet is already at `nodes.min`.",
            instance_model.name,
        )
        return None

    idle_duration = _get_instance_idle_duration(instance_model)
    if idle_duration <= datetime.timedelta(seconds=instance_model.termination_idle_time):
        return None

    result = _ProcessResult()
    _set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATING,
        termination_reason=InstanceTerminationReason.IDLE_TIMEOUT,
        termination_reason_message=f"Instance idle for {idle_duration.seconds}s",
    )
    return result


def _can_terminate_fleet_instances_on_idle_duration(fleet_model: FleetModel) -> bool:
    fleet = fleet_model_to_fleet(fleet_model)
    if fleet.spec.configuration.nodes is None or fleet.spec.autocreated:
        return True
    active_instances = [
        instance for instance in fleet_model.instances if instance.status.is_active()
    ]
    return len(active_instances) > fleet.spec.configuration.nodes.min


async def _add_ssh_instance(instance_model: InstanceModel) -> _ProcessResult:
    result = _ProcessResult()
    logger.info("Adding ssh instance %s...", instance_model.name)

    retry_duration_deadline = instance_model.created_at + timedelta(
        seconds=PROVISIONING_TIMEOUT_SECONDS
    )
    if retry_duration_deadline < get_current_datetime():
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
            termination_reason_message=(
                f"Failed to add SSH instance in {PROVISIONING_TIMEOUT_SECONDS}s"
            ),
        )
        return result

    remote_details = get_instance_remote_connection_info(instance_model)
    assert remote_details is not None

    try:
        pkeys = _ssh_keys_to_pkeys(remote_details.ssh_keys)
        ssh_proxy_pkeys = None
        if remote_details.ssh_proxy_keys is not None:
            ssh_proxy_pkeys = _ssh_keys_to_pkeys(remote_details.ssh_proxy_keys)
    except (ValueError, PasswordRequiredException):
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Unsupported private SSH key type",
        )
        return result

    authorized_keys = [pkey.public.strip() for pkey in remote_details.ssh_keys]
    authorized_keys.append(instance_model.project.ssh_public_key.strip())

    try:
        future = run_async(
            _deploy_ssh_instance,
            remote_details,
            pkeys,
            ssh_proxy_pkeys,
            authorized_keys,
        )
        deploy_timeout = 20 * 60
        health, host_info, arch = await asyncio.wait_for(future, timeout=deploy_timeout)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        logger.warning(
            "%s: deploy timeout when adding SSH instance: %s",
            fmt(instance_model),
            repr(exc),
        )
        return result
    except SSHProvisioningError as exc:
        logger.warning(
            "%s: provisioning error when adding SSH instance: %s",
            fmt(instance_model),
            repr(exc),
        )
        return result
    except Exception:
        logger.exception("%s: unexpected error when adding SSH instance", fmt(instance_model))
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Unexpected error when adding SSH instance",
        )
        return result

    instance_type = host_info_to_instance_type(host_info, arch)
    try:
        instance_network, internal_ip = _resolve_ssh_instance_network(instance_model, host_info)
    except _SSHInstanceNetworkResolutionError as exc:
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message=str(exc),
        )
        return result

    divisible, blocks = is_divisible_into_blocks(
        cpu_count=instance_type.resources.cpus,
        gpu_count=len(instance_type.resources.gpus),
        blocks="auto" if instance_model.total_blocks is None else instance_model.total_blocks,
    )
    if not divisible:
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Cannot split into blocks",
        )
        return result

    region = instance_model.region
    assert region is not None
    job_provisioning_data = JobProvisioningData(
        backend=BackendType.REMOTE,
        instance_type=instance_type,
        instance_id="instance_id",
        hostname=remote_details.host,
        region=region,
        price=0,
        internal_ip=internal_ip,
        instance_network=instance_network,
        username=remote_details.ssh_user,
        ssh_port=remote_details.port,
        dockerized=True,
        backend_data=None,
        ssh_proxy=remote_details.ssh_proxy,
    )
    instance_offer = InstanceOfferWithAvailability(
        backend=BackendType.REMOTE,
        instance=instance_type,
        region=region,
        price=0,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.SHIM,
    )

    _set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.IDLE if health else InstanceStatus.PROVISIONING,
    )
    result.instance_update_map["backend"] = BackendType.REMOTE
    result.instance_update_map["price"] = 0
    result.instance_update_map["offer"] = instance_offer.json()
    result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
    result.instance_update_map["started_at"] = NOW_PLACEHOLDER
    result.instance_update_map["total_blocks"] = blocks
    return result


class _SSHInstanceNetworkResolutionError(Exception):
    pass


def _resolve_ssh_instance_network(
    instance_model: InstanceModel,
    host_info: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    instance_network = None
    internal_ip = None
    try:
        default_job_provisioning_data = JobProvisioningData.__response__.parse_raw(
            instance_model.job_provisioning_data
        )
        instance_network = default_job_provisioning_data.instance_network
        internal_ip = default_job_provisioning_data.internal_ip
    except ValidationError:
        pass

    host_network_addresses = host_info.get("addresses", [])
    if internal_ip is None:
        internal_ip = get_ip_from_network(
            network=instance_network,
            addresses=host_network_addresses,
        )
    if instance_network is not None and internal_ip is None:
        raise _SSHInstanceNetworkResolutionError(
            "Failed to locate internal IP address on the given network"
        )
    if internal_ip is not None and not is_ip_among_addresses(
        ip_address=internal_ip,
        addresses=host_network_addresses,
    ):
        raise _SSHInstanceNetworkResolutionError(
            "Specified internal IP not found among instance interfaces"
        )
    return instance_network, internal_ip


def _deploy_ssh_instance(
    remote_details: RemoteConnectionInfo,
    pkeys: list[PKey],
    ssh_proxy_pkeys: Optional[list[PKey]],
    authorized_keys: list[str],
) -> tuple[InstanceCheck, dict[str, Any], GoArchType]:
    with get_paramiko_connection(
        remote_details.ssh_user,
        remote_details.host,
        remote_details.port,
        pkeys,
        remote_details.ssh_proxy,
        ssh_proxy_pkeys,
    ) as client:
        logger.debug("Connected to %s %s", remote_details.ssh_user, remote_details.host)

        arch = detect_cpu_arch(client)
        logger.debug("%s: CPU arch is %s", remote_details.host, arch)

        shim_pre_start_commands = get_shim_pre_start_commands(arch=arch)
        run_pre_start_commands(client, shim_pre_start_commands, authorized_keys)
        logger.debug("The script for installing dstack has been executed")

        shim_envs = get_shim_env(arch=arch)
        try:
            fleet_configuration_envs = remote_details.env.as_dict()
        except ValueError as exc:
            raise SSHProvisioningError(f"Invalid Env: {exc}") from exc
        shim_envs.update(fleet_configuration_envs)
        dstack_working_dir = get_dstack_working_dir()
        dstack_shim_binary_path = get_dstack_shim_binary_path()
        dstack_runner_binary_path = get_dstack_runner_binary_path()
        upload_envs(client, dstack_working_dir, shim_envs)
        logger.debug("The dstack-shim environment variables have been installed")

        remove_host_info_if_exists(client, dstack_working_dir)
        remove_dstack_runner_if_exists(client, dstack_runner_binary_path)

        run_shim_as_systemd_service(
            client=client,
            binary_path=dstack_shim_binary_path,
            working_dir=dstack_working_dir,
            dev=settings.DSTACK_VERSION is None,
        )

        host_info = get_host_info(client, dstack_working_dir)
        logger.debug("Received a host_info %s", host_info)

        healthcheck_out = get_shim_healthcheck(client)
        try:
            healthcheck = HealthcheckResponse.__response__.parse_raw(healthcheck_out)
        except ValueError as exc:
            raise SSHProvisioningError(f"Cannot parse HealthcheckResponse: {exc}") from exc
        instance_check = runner_client.healthcheck_response_to_instance_check(healthcheck)
        return instance_check, host_info, arch


async def _create_cloud_instance(instance_model: InstanceModel) -> _ProcessResult:
    result = _ProcessResult()
    master_instance_model = _get_fleet_master_instance(instance_model)
    if _need_to_wait_fleet_provisioning(instance_model, master_instance_model):
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
        _set_status_update(
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
        selected_offer = _get_instance_offer_for_instance(
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

        _set_status_update(
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

    _set_status_update(
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
            sibling_update_map = _SiblingInstanceUpdateMap(id=sibling_instance_model.id)
            _set_status_update(
                update_map=sibling_update_map,
                instance_model=sibling_instance_model,
                new_status=InstanceStatus.TERMINATED,
                termination_reason=InstanceTerminationReason.MASTER_FAILED,
            )
            if len(sibling_update_map) > 1:
                result.sibling_update_rows.append(sibling_update_map)
                _append_sibling_status_event(
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


def _get_fleet_master_instance(instance_model: InstanceModel) -> InstanceModel:
    if instance_model.fleet is None:
        return instance_model
    fleet_instances = list(instance_model.fleet.instances)
    if all(fleet_instance.id != instance_model.id for fleet_instance in fleet_instances):
        fleet_instances.append(instance_model)
    return min(
        fleet_instances,
        key=lambda fleet_instance: (fleet_instance.instance_num, fleet_instance.created_at),
    )


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
        create_payload=_PlacementGroupCreate(
            id=placement_group_id,
            name=placement_group.name,
            project_id=instance_model.project_id,
            fleet_id=get_or_error(instance_model.fleet_id),
            configuration=placement_group.configuration.json(),
            provisioning_data=provisioning_data.json(),
        ),
    )


async def _check_instance(instance_model: InstanceModel) -> _ProcessResult:
    result = _ProcessResult()
    if (
        instance_model.status == InstanceStatus.BUSY
        and instance_model.jobs
        and all(job.status.is_finished() for job in instance_model.jobs)
    ):
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.JOB_FINISHED,
        )
        logger.warning(
            "Detected busy instance %s with finished job. Marked as TERMINATING",
            instance_model.name,
            extra={
                "instance_name": instance_model.name,
                "instance_status": instance_model.status.value,
            },
        )
        return result

    job_provisioning_data = get_or_error(get_instance_provisioning_data(instance_model))
    if job_provisioning_data.hostname is None:
        return await _process_wait_for_instance_provisioning_data(
            instance_model=instance_model,
            job_provisioning_data=job_provisioning_data,
        )

    if not job_provisioning_data.dockerized:
        if instance_model.status == InstanceStatus.PROVISIONING:
            _set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.BUSY,
            )
        return result

    check_instance_health = await _should_check_instance_health(instance_model.id)
    instance_check = await _run_instance_check(
        instance_model=instance_model,
        job_provisioning_data=job_provisioning_data,
        check_instance_health=check_instance_health,
    )
    health_status = _get_health_status_for_instance_check(
        instance_model=instance_model,
        instance_check=instance_check,
        check_instance_health=check_instance_health,
    )
    _log_instance_check_result(
        instance_model=instance_model,
        instance_check=instance_check,
        health_status=health_status,
        check_instance_health=check_instance_health,
    )

    if instance_check.has_health_checks():
        assert instance_check.health_response is not None
        result.health_check_create = _HealthCheckCreate(
            instance_id=instance_model.id,
            collected_at=get_current_datetime(),
            status=health_status,
            response=instance_check.health_response.json(),
        )

    _set_health_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        health=health_status,
    )
    _set_unreachable_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        unreachable=not instance_check.reachable,
    )

    if instance_check.reachable:
        result.instance_update_map["termination_deadline"] = None
        if instance_model.status == InstanceStatus.PROVISIONING:
            _set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.IDLE if not instance_model.jobs else InstanceStatus.BUSY,
            )
        return result

    now = get_current_datetime()
    if not is_ssh_instance(instance_model) and instance_model.termination_deadline is None:
        result.instance_update_map["termination_deadline"] = now + TERMINATION_DEADLINE_OFFSET

    if (
        instance_model.status == InstanceStatus.PROVISIONING
        and instance_model.started_at is not None
    ):
        provisioning_deadline = _get_provisioning_deadline(
            instance_model=instance_model,
            job_provisioning_data=job_provisioning_data,
        )
        if now > provisioning_deadline:
            _set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.TERMINATING,
                termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
                termination_reason_message="Instance did not become reachable in time",
            )
    elif instance_model.status.is_available():
        deadline = instance_model.termination_deadline
        if deadline is not None and now > deadline:
            _set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.TERMINATING,
                termination_reason=InstanceTerminationReason.UNREACHABLE,
            )
    return result


async def _should_check_instance_health(instance_id: uuid.UUID) -> bool:
    health_check_cutoff = get_current_datetime() - timedelta(
        seconds=server_settings.SERVER_INSTANCE_HEALTH_MIN_COLLECT_INTERVAL_SECONDS
    )
    async with get_session_ctx() as session:
        res = await session.execute(
            select(func.count(1)).where(
                InstanceHealthCheckModel.instance_id == instance_id,
                InstanceHealthCheckModel.collected_at > health_check_cutoff,
            )
        )
    return res.scalar_one() == 0


async def _run_instance_check(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
    check_instance_health: bool,
) -> InstanceCheck:
    ssh_private_keys = get_instance_ssh_private_keys(instance_model)
    instance_check = await run_async(
        _check_instance_inner,
        ssh_private_keys,
        job_provisioning_data,
        None,
        instance=instance_model,
        check_instance_health=check_instance_health,
    )
    if instance_check is False:
        return InstanceCheck(reachable=False, message="SSH or tunnel error")
    return instance_check


def _get_health_status_for_instance_check(
    instance_model: InstanceModel,
    instance_check: InstanceCheck,
    check_instance_health: bool,
) -> HealthStatus:
    if instance_check.reachable and check_instance_health:
        return instance_check.get_health_status()
    return instance_model.health


def _log_instance_check_result(
    instance_model: InstanceModel,
    instance_check: InstanceCheck,
    health_status: HealthStatus,
    check_instance_health: bool,
) -> None:
    loglevel = logging.DEBUG
    if not instance_check.reachable and instance_model.status.is_available():
        loglevel = logging.WARNING
    elif check_instance_health and not health_status.is_healthy():
        loglevel = logging.WARNING
    logger.log(
        loglevel,
        "Instance %s check: reachable=%s health_status=%s message=%r",
        instance_model.name,
        instance_check.reachable,
        health_status.name,
        instance_check.message,
        extra={"instance_name": instance_model.name, "health_status": health_status},
    )


async def _process_wait_for_instance_provisioning_data(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
) -> _ProcessResult:
    result = _ProcessResult()
    logger.debug("Waiting for instance %s to become running", instance_model.name)
    provisioning_deadline = _get_provisioning_deadline(
        instance_model=instance_model,
        job_provisioning_data=job_provisioning_data,
    )
    if get_current_datetime() > provisioning_deadline:
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
            termination_reason_message="Backend did not complete provisioning in time",
        )
        return result

    backend = await backends_services.get_project_backend_by_type(
        project=instance_model.project,
        backend_type=job_provisioning_data.backend,
    )
    if backend is None:
        logger.warning(
            "Instance %s failed because instance's backend is not available",
            instance_model.name,
        )
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Backend not available",
        )
        return result

    try:
        await run_async(
            backend.compute().update_provisioning_data,
            job_provisioning_data,
            instance_model.project.ssh_public_key,
            instance_model.project.ssh_private_key,
        )
        result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
    except ProvisioningError as exc:
        logger.warning(
            "Error while waiting for instance %s to become running: %s",
            instance_model.name,
            repr(exc),
        )
        _set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Error while waiting for instance to become running",
        )
    except Exception:
        logger.exception(
            "Got exception when updating instance %s provisioning data",
            instance_model.name,
        )
    return result


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _check_instance_inner(
    ports: Dict[int, int],
    *,
    instance: InstanceModel,
    check_instance_health: bool = False,
) -> InstanceCheck:
    instance_health_response: Optional[InstanceHealthResponse] = None
    shim_client = runner_client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    method = shim_client.healthcheck
    try:
        healthcheck_response = method(unmask_exceptions=True)
        if check_instance_health:
            method = shim_client.get_instance_health
            instance_health_response = method()
    except requests.RequestException as exc:
        template = "shim.%s(): request error: %s"
        args = (method.__func__.__name__, exc)
        logger.debug(template, *args)
        return InstanceCheck(reachable=False, message=template % args)
    except Exception as exc:
        template = "shim.%s(): unexpected exception %s: %s"
        args = (method.__func__.__name__, exc.__class__.__name__, exc)
        logger.exception(template, *args)
        return InstanceCheck(reachable=False, message=template % args)

    try:
        remove_dangling_tasks_from_instance(shim_client, instance)
    except Exception as exc:
        logger.exception("%s: error removing dangling tasks: %s", fmt(instance), exc)

    _maybe_install_components(instance, shim_client)
    return runner_client.healthcheck_response_to_instance_check(
        healthcheck_response,
        instance_health_response,
    )


def _maybe_install_components(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
) -> None:
    try:
        components = shim_client.get_components()
    except requests.RequestException as exc:
        logger.warning(
            "Instance %s: shim.get_components(): request error: %s", instance_model.name, exc
        )
        return
    if components is None:
        logger.debug("Instance %s: no components info", instance_model.name)
        return

    installed_shim_version: Optional[str] = None
    installation_requested = False

    if (runner_info := components.runner) is not None:
        installation_requested |= _maybe_install_runner(instance_model, shim_client, runner_info)
    else:
        logger.debug("Instance %s: no runner info", instance_model.name)

    if (shim_info := components.shim) is not None:
        if shim_info.status == ComponentStatus.INSTALLED:
            installed_shim_version = shim_info.version
        installation_requested |= _maybe_install_shim(instance_model, shim_client, shim_info)
    else:
        logger.debug("Instance %s: no shim info", instance_model.name)

    running_shim_version = shim_client.get_version_string()
    if (
        installed_shim_version is None
        or installed_shim_version == running_shim_version
        or installation_requested
        or any(component.status == ComponentStatus.INSTALLING for component in components)
        or not shim_client.is_safe_to_restart()
    ):
        return

    if shim_client.shutdown(force=False):
        logger.debug(
            "Instance %s: restarting shim %s -> %s",
            instance_model.name,
            running_shim_version,
            installed_shim_version,
        )
    else:
        logger.debug("Instance %s: cannot restart shim", instance_model.name)


def _maybe_install_runner(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
    runner_info: ComponentInfo,
) -> bool:
    expected_version = get_dstack_runner_version()
    if expected_version is None:
        logger.debug("Cannot determine the expected runner version")
        return False

    installed_version = runner_info.version
    logger.debug(
        "Instance %s: runner status=%s installed_version=%s",
        instance_model.name,
        runner_info.status.value,
        installed_version or "(no version)",
    )
    if runner_info.status == ComponentStatus.INSTALLING:
        logger.debug("Instance %s: runner is already being installed", instance_model.name)
        return False
    if installed_version and installed_version == expected_version:
        logger.debug("Instance %s: expected runner version already installed", instance_model.name)
        return False

    url = get_dstack_runner_download_url(
        arch=_get_instance_cpu_arch(instance_model),
        version=expected_version,
    )
    logger.debug(
        "Instance %s: installing runner %s -> %s from %s",
        instance_model.name,
        installed_version or "(no version)",
        expected_version,
        url,
    )
    try:
        shim_client.install_runner(url)
        return True
    except requests.RequestException as exc:
        logger.warning("Instance %s: shim.install_runner(): %s", instance_model.name, exc)
    return False


def _maybe_install_shim(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
    shim_info: ComponentInfo,
) -> bool:
    expected_version = get_dstack_shim_version()
    if expected_version is None:
        logger.debug("Cannot determine the expected shim version")
        return False

    installed_version = shim_info.version
    logger.debug(
        "Instance %s: shim status=%s installed_version=%s running_version=%s",
        instance_model.name,
        shim_info.status.value,
        installed_version or "(no version)",
        shim_client.get_version_string(),
    )
    if shim_info.status == ComponentStatus.INSTALLING:
        logger.debug("Instance %s: shim is already being installed", instance_model.name)
        return False
    if installed_version and installed_version == expected_version:
        logger.debug("Instance %s: expected shim version already installed", instance_model.name)
        return False

    url = get_dstack_shim_download_url(
        arch=_get_instance_cpu_arch(instance_model),
        version=expected_version,
    )
    logger.debug(
        "Instance %s: installing shim %s -> %s from %s",
        instance_model.name,
        installed_version or "(no version)",
        expected_version,
        url,
    )
    try:
        shim_client.install_shim(url)
        return True
    except requests.RequestException as exc:
        logger.warning("Instance %s: shim.install_shim(): %s", instance_model.name, exc)
    return False


def _get_instance_cpu_arch(instance_model: InstanceModel) -> Optional[gpuhunt.CPUArchitecture]:
    job_provisioning_data = get_instance_provisioning_data(instance_model)
    if job_provisioning_data is None:
        return None
    return job_provisioning_data.instance_type.resources.cpu_arch


async def _terminate_instance(instance_model: InstanceModel) -> _ProcessResult:
    result = _ProcessResult()
    now = get_current_datetime()
    if (
        instance_model.last_termination_retry_at is not None
        and _next_termination_retry_at(instance_model.last_termination_retry_at) > now
    ):
        return result

    job_provisioning_data = get_instance_provisioning_data(instance_model)
    if job_provisioning_data is not None and job_provisioning_data.backend != BackendType.REMOTE:
        backend = await backends_services.get_project_backend_by_type(
            project=instance_model.project,
            backend_type=job_provisioning_data.backend,
        )
        if backend is None:
            logger.error(
                "Failed to terminate instance %s. Backend %s not available.",
                instance_model.name,
                job_provisioning_data.backend,
            )
        else:
            logger.debug("Terminating runner instance %s", job_provisioning_data.hostname)
            try:
                await run_async(
                    backend.compute().terminate_instance,
                    job_provisioning_data.instance_id,
                    job_provisioning_data.region,
                    job_provisioning_data.backend_data,
                )
            except Exception as exc:
                first_retry_at = instance_model.first_termination_retry_at
                if first_retry_at is None:
                    first_retry_at = now
                    result.instance_update_map["first_termination_retry_at"] = NOW_PLACEHOLDER
                result.instance_update_map["last_termination_retry_at"] = NOW_PLACEHOLDER
                if _next_termination_retry_at(now) < _get_termination_deadline(first_retry_at):
                    if isinstance(exc, NotYetTerminated):
                        logger.debug(
                            "Instance %s termination in progress: %s",
                            instance_model.name,
                            exc,
                        )
                    else:
                        logger.warning(
                            "Failed to terminate instance %s. Will retry. Error: %r",
                            instance_model.name,
                            exc,
                            exc_info=not isinstance(exc, BackendError),
                        )
                    return result
                logger.error(
                    "Failed all attempts to terminate instance %s."
                    " Please terminate the instance manually to avoid unexpected charges."
                    " Error: %r",
                    instance_model.name,
                    exc,
                    exc_info=not isinstance(exc, BackendError),
                )

    result.instance_update_map["deleted"] = True
    result.instance_update_map["deleted_at"] = NOW_PLACEHOLDER
    result.instance_update_map["finished_at"] = NOW_PLACEHOLDER
    _set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATED,
    )
    return result


def _next_termination_retry_at(last_termination_retry_at: datetime.datetime) -> datetime.datetime:
    return last_termination_retry_at + TERMINATION_RETRY_TIMEOUT


def _get_termination_deadline(first_termination_retry_at: datetime.datetime) -> datetime.datetime:
    return first_termination_retry_at + TERMINATION_RETRY_MAX_DURATION


def _need_to_wait_fleet_provisioning(
    instance_model: InstanceModel,
    master_instance_model: InstanceModel,
) -> bool:
    if instance_model.fleet is None:
        return False
    if (
        instance_model.id == master_instance_model.id
        or master_instance_model.job_provisioning_data is not None
        or master_instance_model.status == InstanceStatus.TERMINATED
    ):
        return False
    return is_cloud_cluster(instance_model.fleet)


def _get_instance_offer_for_instance(
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


def _get_instance_idle_duration(instance_model: InstanceModel) -> datetime.timedelta:
    last_time = instance_model.created_at
    if instance_model.last_job_processed_at is not None:
        last_time = instance_model.last_job_processed_at
    return get_current_datetime() - last_time


def _get_provisioning_deadline(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
) -> datetime.datetime:
    assert instance_model.started_at is not None
    timeout_interval = get_provisioning_timeout(
        backend_type=job_provisioning_data.get_base_backend(),
        instance_type_name=job_provisioning_data.instance_type.name,
    )
    return instance_model.started_at + timeout_interval


def _ssh_keys_to_pkeys(ssh_keys: list[SSHKey]) -> list[PKey]:
    return [pkey_from_str(ssh_key.private) for ssh_key in ssh_keys if ssh_key.private is not None]


def _set_status_update(
    update_map: Union[_InstanceUpdateMap, _SiblingInstanceUpdateMap],
    instance_model: InstanceModel,
    new_status: InstanceStatus,
    termination_reason: object = _UNSET,
    termination_reason_message: object = _UNSET,
) -> None:
    old_status = instance_model.status
    if old_status == new_status:
        if termination_reason is not _UNSET:
            update_map["termination_reason"] = cast(
                Optional[InstanceTerminationReason], termination_reason
            )
        if termination_reason_message is not _UNSET:
            update_map["termination_reason_message"] = cast(
                Optional[str], termination_reason_message
            )
        return

    effective_termination_reason = instance_model.termination_reason
    if termination_reason is not _UNSET:
        effective_termination_reason = cast(
            Optional[InstanceTerminationReason], termination_reason
        )
        update_map["termination_reason"] = effective_termination_reason

    effective_termination_reason_message = instance_model.termination_reason_message
    if termination_reason_message is not _UNSET:
        effective_termination_reason_message = cast(Optional[str], termination_reason_message)
        update_map["termination_reason_message"] = effective_termination_reason_message

    update_map["status"] = new_status


def _set_health_update(
    update_map: _InstanceUpdateMap,
    instance_model: InstanceModel,
    health: HealthStatus,
) -> None:
    if instance_model.health == health:
        return
    update_map["health"] = health


def _set_unreachable_update(
    update_map: _InstanceUpdateMap,
    instance_model: InstanceModel,
    unreachable: bool,
) -> None:
    if not instance_model.status.is_available() or instance_model.unreachable == unreachable:
        return
    update_map["unreachable"] = unreachable


def _append_sibling_status_event(
    deferred_events: list[_SiblingDeferredEvent],
    instance_model: InstanceModel,
    new_status: InstanceStatus,
    termination_reason: Optional[InstanceTerminationReason],
    termination_reason_message: Optional[str],
) -> None:
    if instance_model.status == new_status:
        return
    deferred_events.append(
        _SiblingDeferredEvent(
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


async def _apply_process_result(item: InstancePipelineItem, result: _ProcessResult) -> None:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(InstanceModel)
            .where(
                InstanceModel.id == item.id,
                InstanceModel.lock_token == item.lock_token,
            )
            .options(
                load_only(
                    InstanceModel.id,
                    InstanceModel.project_id,
                    InstanceModel.name,
                    InstanceModel.status,
                    InstanceModel.termination_reason,
                    InstanceModel.termination_reason_message,
                    InstanceModel.health,
                    InstanceModel.unreachable,
                )
            )
        )
        instance_model = res.scalar_one_or_none()
        if instance_model is None:
            log_lock_token_mismatch(logger, item)
            return
        for placement_group_create in result.placement_group_creates:
            session.add(PlacementGroupModel(**placement_group_create))
        if result.health_check_create is not None:
            session.add(InstanceHealthCheckModel(**result.health_check_create))
        await session.flush()

        now = get_current_datetime()
        resolve_now_placeholders(result.instance_update_map, now=now)
        resolve_now_placeholders(result.sibling_update_rows, now=now)
        res = await session.execute(
            update(InstanceModel)
            .execution_options(synchronize_session=False)
            .where(
                InstanceModel.id == item.id,
                InstanceModel.lock_token == item.lock_token,
            )
            .values(**result.instance_update_map)
            .returning(InstanceModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            await session.rollback()
            return

        if result.sibling_update_rows:
            await session.execute(
                update(InstanceModel).execution_options(synchronize_session=False),
                result.sibling_update_rows,
            )

        if result.schedule_pg_deletion_fleet_id is not None:
            await schedule_fleet_placement_groups_deletion(
                session=session,
                fleet_id=result.schedule_pg_deletion_fleet_id,
                except_placement_group_ids=result.schedule_pg_deletion_except_ids,
            )

        emit_instance_status_change_event(
            session=session,
            instance_model=instance_model,
            old_status=instance_model.status,
            new_status=_get_effective_instance_status(instance_model, result.instance_update_map),
            termination_reason=_get_effective_instance_termination_reason(
                instance_model, result.instance_update_map
            ),
            termination_reason_message=_get_effective_instance_termination_reason_message(
                instance_model, result.instance_update_map
            ),
        )
        _emit_instance_health_change_event(
            session=session,
            instance_model=instance_model,
            old_health=instance_model.health,
            new_health=_get_effective_instance_health(instance_model, result.instance_update_map),
        )
        _emit_instance_reachability_change_event(
            session=session,
            instance_model=instance_model,
            old_status=instance_model.status,
            old_unreachable=instance_model.unreachable,
            new_unreachable=_get_effective_instance_unreachable(
                instance_model, result.instance_update_map
            ),
        )

        for deferred_event in result.sibling_deferred_events:
            events.emit(
                session=session,
                message=deferred_event.message,
                actor=events.SystemActor(),
                targets=[
                    events.Target(
                        type=EventTargetType.INSTANCE,
                        project_id=deferred_event.project_id,
                        id=deferred_event.instance_id,
                        name=deferred_event.instance_name,
                    )
                ],
            )
        await session.commit()


def _get_effective_instance_status(
    instance_model: InstanceModel,
    update_map: _InstanceUpdateMap,
) -> InstanceStatus:
    return cast(InstanceStatus, update_map.get("status", instance_model.status))


def _get_effective_instance_termination_reason(
    instance_model: InstanceModel,
    update_map: _InstanceUpdateMap,
) -> Optional[InstanceTerminationReason]:
    return cast(
        Optional[InstanceTerminationReason],
        update_map.get("termination_reason", instance_model.termination_reason),
    )


def _get_effective_instance_termination_reason_message(
    instance_model: InstanceModel,
    update_map: _InstanceUpdateMap,
) -> Optional[str]:
    return cast(
        Optional[str],
        update_map.get("termination_reason_message", instance_model.termination_reason_message),
    )


def _get_effective_instance_health(
    instance_model: InstanceModel,
    update_map: _InstanceUpdateMap,
) -> HealthStatus:
    return cast(HealthStatus, update_map.get("health", instance_model.health))


def _get_effective_instance_unreachable(
    instance_model: InstanceModel,
    update_map: _InstanceUpdateMap,
) -> bool:
    return cast(bool, update_map.get("unreachable", instance_model.unreachable))


def _emit_instance_health_change_event(
    session: AsyncSession,
    instance_model: InstanceModel,
    old_health: HealthStatus,
    new_health: HealthStatus,
) -> None:
    if old_health == new_health:
        return
    events.emit(
        session=session,
        message=f"Instance health changed {old_health.upper()} -> {new_health.upper()}",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(instance_model)],
    )


def _emit_instance_reachability_change_event(
    session: AsyncSession,
    instance_model: InstanceModel,
    old_status: InstanceStatus,
    old_unreachable: bool,
    new_unreachable: bool,
) -> None:
    if not old_status.is_available() or old_unreachable == new_unreachable:
        return
    events.emit(
        session=session,
        message="Instance became unreachable" if new_unreachable else "Instance became reachable",
        actor=events.SystemActor(),
        targets=[events.Target.from_model(instance_model)],
    )
