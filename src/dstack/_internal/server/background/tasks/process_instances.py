import asyncio
import datetime
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

import requests
from paramiko.pkey import PKey
from paramiko.ssh_exception import PasswordRequiredException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal import settings
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    ComputeWithPlacementGroupSupport,
    GoArchType,
    generate_unique_placement_group_name,
    get_dstack_runner_binary_path,
    get_dstack_shim_binary_path,
    get_dstack_working_dir,
    get_shim_env,
    get_shim_pre_start_commands,
)
from dstack._internal.core.backends.features import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT,
)
from dstack._internal.core.backends.remote.provisioning import (
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
from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT

# FIXME: ProvisioningError is a subclass of ComputeError and should not be used outside of Compute
from dstack._internal.core.errors import (
    BackendError,
    NotYetTerminated,
    PlacementGroupNotSupportedError,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import InstanceGroupPlacement
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceStatus,
    RemoteConnectionInfo,
    SSHKey,
)
from dstack._internal.core.models.placement import (
    PlacementGroupConfiguration,
    PlacementStrategy,
)
from dstack._internal.core.models.profiles import (
    RetryEvent,
    TerminationPolicy,
)
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    Retry,
)
from dstack._internal.core.services.profiles import get_retry
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.tasks.common import get_provisioning_timeout
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    ProjectModel,
)
from dstack._internal.server.schemas.runner import HealthcheckResponse
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.fleets import (
    fleet_model_to_fleet,
    get_create_instance_offers,
)
from dstack._internal.server.services.instances import (
    get_instance_configuration,
    get_instance_profile,
    get_instance_provisioning_data,
    get_instance_requirements,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.offers import is_divisible_into_blocks
from dstack._internal.server.services.placement import (
    get_fleet_placement_group_models,
    placement_group_model_to_placement_group,
    schedule_fleet_placement_groups_deletion,
)
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.runner.client import HealthStatus
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.utils.common import (
    get_current_datetime,
    get_or_error,
    run_async,
)
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.network import get_ip_from_network, is_ip_among_addresses
from dstack._internal.utils.ssh import (
    pkey_from_str,
)

MIN_PROCESSING_INTERVAL = timedelta(seconds=10)

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)
TERMINATION_RETRY_TIMEOUT = timedelta(seconds=30)
TERMINATION_RETRY_MAX_DURATION = timedelta(minutes=15)
PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds


logger = get_logger(__name__)


async def process_instances(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_instance())
    await asyncio.gather(*tasks)


async def _process_next_instance():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(InstanceModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
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
                    InstanceModel.id.not_in(lockset),
                    InstanceModel.last_processed_at
                    < get_current_datetime() - MIN_PROCESSING_INTERVAL,
                )
                .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
                .options(joinedload(InstanceModel.project).load_only(ProjectModel.ssh_private_key))
                .order_by(InstanceModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True, key_share=True, of=InstanceModel)
            )
            instance = res.scalar()
            if instance is None:
                return
            lockset.add(instance.id)
        try:
            instance_model_id = instance.id
            await _process_instance(session=session, instance=instance)
        finally:
            lockset.difference_update([instance_model_id])


async def _process_instance(session: AsyncSession, instance: InstanceModel):
    if instance.status in (
        InstanceStatus.PENDING,
        InstanceStatus.TERMINATING,
    ):
        # Refetch to load related attributes.
        # Load related attributes only for statuses that always need them.
        res = await session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == instance.id)
            .options(joinedload(InstanceModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(InstanceModel.jobs).load_only(JobModel.id, JobModel.status))
            .options(joinedload(InstanceModel.fleet).joinedload(FleetModel.instances))
            .execution_options(populate_existing=True)
        )
        instance = res.unique().scalar_one()

    if instance.status == InstanceStatus.PENDING:
        if instance.remote_connection_info is not None:
            await _add_remote(instance)
        else:
            await _create_instance(
                session=session,
                instance=instance,
            )
    elif instance.status in (
        InstanceStatus.PROVISIONING,
        InstanceStatus.IDLE,
        InstanceStatus.BUSY,
    ):
        idle_duration_expired = _check_and_mark_terminating_if_idle_duration_expired(instance)
        if not idle_duration_expired:
            await _check_instance(session, instance)
    elif instance.status == InstanceStatus.TERMINATING:
        await _terminate(instance)

    instance.last_processed_at = get_current_datetime()
    await session.commit()


def _check_and_mark_terminating_if_idle_duration_expired(instance: InstanceModel):
    if not (
        instance.status == InstanceStatus.IDLE
        and instance.termination_policy == TerminationPolicy.DESTROY_AFTER_IDLE
        and not instance.jobs
    ):
        return False
    idle_duration = _get_instance_idle_duration(instance)
    idle_seconds = instance.termination_idle_time
    delta = datetime.timedelta(seconds=idle_seconds)
    if idle_duration > delta:
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Idle timeout"
        logger.info(
            "Instance %s idle duration expired: idle time %ss. Terminating",
            instance.name,
            str(idle_duration.seconds),
            extra={
                "instance_name": instance.name,
                "instance_status": instance.status.value,
            },
        )
        return True
    return False


async def _add_remote(instance: InstanceModel) -> None:
    logger.info("Adding ssh instance %s...", instance.name)
    if instance.status == InstanceStatus.PENDING:
        instance.status = InstanceStatus.PROVISIONING

    retry_duration_deadline = instance.created_at.replace(
        tzinfo=datetime.timezone.utc
    ) + timedelta(seconds=PROVISIONING_TIMEOUT_SECONDS)
    if retry_duration_deadline < get_current_datetime():
        instance.status = InstanceStatus.TERMINATED
        instance.termination_reason = "Provisioning timeout expired"
        logger.warning(
            "Failed to start instance %s in %d seconds. Terminating...",
            instance.name,
            PROVISIONING_TIMEOUT_SECONDS,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.TERMINATED.value,
            },
        )
        return

    try:
        remote_details = RemoteConnectionInfo.parse_raw(cast(str, instance.remote_connection_info))
        # Prepare connection key
        try:
            pkeys = _ssh_keys_to_pkeys(remote_details.ssh_keys)
            if remote_details.ssh_proxy_keys is not None:
                ssh_proxy_pkeys = _ssh_keys_to_pkeys(remote_details.ssh_proxy_keys)
            else:
                ssh_proxy_pkeys = None
        except (ValueError, PasswordRequiredException):
            instance.status = InstanceStatus.TERMINATED
            instance.termination_reason = "Unsupported private SSH key type"
            logger.warning(
                "Failed to add instance %s: unsupported private SSH key type",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )
            return

        authorized_keys = [pk.public.strip() for pk in remote_details.ssh_keys]
        authorized_keys.append(instance.project.ssh_public_key.strip())

        try:
            future = run_async(
                _deploy_instance, remote_details, pkeys, ssh_proxy_pkeys, authorized_keys
            )
            deploy_timeout = 20 * 60  # 20 minutes
            result = await asyncio.wait_for(future, timeout=deploy_timeout)
            health, host_info, cpu_arch = result
        except (asyncio.TimeoutError, TimeoutError) as e:
            raise ProvisioningError(f"Deploy timeout: {e}") from e
        except Exception as e:
            raise ProvisioningError(f"Deploy instance raised an error: {e}") from e
        else:
            logger.info(
                "The instance %s (%s) was successfully added",
                instance.name,
                remote_details.host,
            )
    except ProvisioningError as e:
        logger.warning(
            "Provisioning instance %s could not be completed because of the error: %s",
            instance.name,
            e,
        )
        instance.status = InstanceStatus.PENDING
        instance.last_retry_at = get_current_datetime()
        return

    instance_type = host_info_to_instance_type(host_info, cpu_arch)
    instance_network = None
    internal_ip = None
    try:
        default_jpd = JobProvisioningData.__response__.parse_raw(instance.job_provisioning_data)
        instance_network = default_jpd.instance_network
        internal_ip = default_jpd.internal_ip
    except ValidationError:
        pass

    host_network_addresses = host_info.get("addresses", [])
    if internal_ip is None:
        internal_ip = get_ip_from_network(
            network=instance_network,
            addresses=host_network_addresses,
        )
    if instance_network is not None and internal_ip is None:
        instance.status = InstanceStatus.TERMINATED
        instance.termination_reason = "Failed to locate internal IP address on the given network"
        logger.warning(
            "Failed to add instance %s: failed to locate internal IP address on the given network",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.TERMINATED.value,
            },
        )
        return
    if internal_ip is not None:
        if not is_ip_among_addresses(ip_address=internal_ip, addresses=host_network_addresses):
            instance.status = InstanceStatus.TERMINATED
            instance.termination_reason = (
                "Specified internal IP not found among instance interfaces"
            )
            logger.warning(
                "Failed to add instance %s: specified internal IP not found among instance interfaces",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )
            return

    divisible, blocks = is_divisible_into_blocks(
        cpu_count=instance_type.resources.cpus,
        gpu_count=len(instance_type.resources.gpus),
        blocks="auto" if instance.total_blocks is None else instance.total_blocks,
    )
    if divisible:
        instance.total_blocks = blocks
    else:
        instance.status = InstanceStatus.TERMINATED
        instance.termination_reason = "Cannot split into blocks"
        logger.warning(
            "Failed to add instance %s: cannot split into blocks",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.TERMINATED.value,
            },
        )
        return

    region = instance.region
    jpd = JobProvisioningData(
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

    instance.status = InstanceStatus.IDLE if health else InstanceStatus.PROVISIONING
    instance.backend = BackendType.REMOTE
    instance_offer = InstanceOfferWithAvailability(
        backend=BackendType.REMOTE,
        instance=instance_type,
        region=region,
        price=0,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.SHIM,
    )
    instance.price = 0
    instance.offer = instance_offer.json()
    instance.job_provisioning_data = jpd.json()
    instance.started_at = get_current_datetime()
    instance.last_retry_at = get_current_datetime()


def _deploy_instance(
    remote_details: RemoteConnectionInfo,
    pkeys: List[PKey],
    ssh_proxy_pkeys: Optional[list[PKey]],
    authorized_keys: List[str],
) -> Tuple[HealthStatus, Dict[str, Any], GoArchType]:
    with get_paramiko_connection(
        remote_details.ssh_user,
        remote_details.host,
        remote_details.port,
        pkeys,
        remote_details.ssh_proxy,
        ssh_proxy_pkeys,
    ) as client:
        logger.info(f"Connected to {remote_details.ssh_user} {remote_details.host}")

        arch = detect_cpu_arch(client)
        logger.info("%s: CPU arch is %s", remote_details.host, arch)

        # Execute pre start commands
        shim_pre_start_commands = get_shim_pre_start_commands(arch=arch)
        run_pre_start_commands(client, shim_pre_start_commands, authorized_keys)
        logger.debug("The script for installing dstack has been executed")

        # Upload envs
        shim_envs = get_shim_env(authorized_keys, arch=arch)
        try:
            fleet_configuration_envs = remote_details.env.as_dict()
        except ValueError as e:
            raise ProvisioningError(f"Invalid Env: {e}") from e
        shim_envs.update(fleet_configuration_envs)
        dstack_working_dir = get_dstack_working_dir()
        dstack_shim_binary_path = get_dstack_shim_binary_path()
        dstack_runner_binary_path = get_dstack_runner_binary_path()
        upload_envs(client, dstack_working_dir, shim_envs)
        logger.debug("The dstack-shim environment variables have been installed")

        # Ensure we have fresh versions of host info.json and dstack-runner
        remove_host_info_if_exists(client, dstack_working_dir)
        remove_dstack_runner_if_exists(client, dstack_runner_binary_path)

        # Run dstack-shim as a systemd service
        run_shim_as_systemd_service(
            client=client,
            binary_path=dstack_shim_binary_path,
            working_dir=dstack_working_dir,
            dev=settings.DSTACK_VERSION is None,
        )

        # Get host info
        host_info = get_host_info(client, dstack_working_dir)
        logger.debug("Received a host_info %s", host_info)

        raw_health = get_shim_healthcheck(client)
        try:
            health_response = HealthcheckResponse.__response__.parse_raw(raw_health)
        except ValueError as e:
            raise ProvisioningError("Cannot read HealthcheckResponse") from e
        health = runner_client.health_response_to_health_status(health_response)

        return health, host_info, arch


async def _create_instance(session: AsyncSession, instance: InstanceModel) -> None:
    if instance.last_retry_at is not None:
        last_retry = instance.last_retry_at
        if get_current_datetime() < last_retry + timedelta(minutes=1):
            return

    if (
        instance.profile is None
        or instance.requirements is None
        or instance.instance_configuration is None
    ):
        instance.status = InstanceStatus.TERMINATED
        instance.termination_reason = "Empty profile, requirements or instance_configuration"
        instance.last_retry_at = get_current_datetime()
        logger.warning(
            "Empty profile, requirements or instance_configuration. Terminate instance: %s",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.TERMINATED.value,
            },
        )
        return

    if _need_to_wait_fleet_provisioning(instance):
        logger.debug("Waiting for the first instance in the fleet to be provisioned")
        return

    try:
        instance_configuration = get_instance_configuration(instance)
        profile = get_instance_profile(instance)
        requirements = get_instance_requirements(instance)
    except ValidationError as e:
        instance.status = InstanceStatus.TERMINATED
        instance.termination_reason = (
            f"Error to parse profile, requirements or instance_configuration: {e}"
        )
        instance.last_retry_at = get_current_datetime()
        logger.warning(
            "Error to parse profile, requirements or instance_configuration. Terminate instance: %s",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.TERMINATED.value,
            },
        )
        return

    retry = get_retry(profile)
    should_retry = retry is not None and RetryEvent.NO_CAPACITY in retry.on_events

    if retry is not None:
        retry_duration_deadline = _get_retry_duration_deadline(instance, retry)
        if get_current_datetime() > retry_duration_deadline:
            instance.status = InstanceStatus.TERMINATED
            instance.termination_reason = "Retry duration expired"
            logger.warning(
                "Retry duration expired. Terminating instance %s",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )
            return

    placement_group_models = []
    placement_group_model = None
    if instance.fleet_id:
        placement_group_models = await get_fleet_placement_group_models(
            session=session,
            fleet_id=instance.fleet_id,
        )
        # The placement group is determined when provisioning the master instance
        # and used for all other instances in the fleet.
        if not _is_fleet_master_instance(instance):
            if placement_group_models:
                placement_group_model = placement_group_models[0]
            if len(placement_group_models) > 1:
                logger.error(
                    (
                        "Expected 0 or 1 placement groups associated with fleet %s, found %s."
                        " An incorrect placement group might have been selected for instance %s"
                    ),
                    instance.fleet_id,
                    len(placement_group_models),
                    instance.name,
                )

    offers = await get_create_instance_offers(
        project=instance.project,
        profile=profile,
        requirements=requirements,
        fleet_model=instance.fleet,
        placement_group=(
            placement_group_model_to_placement_group(placement_group_model)
            if placement_group_model
            else None
        ),
        blocks="auto" if instance.total_blocks is None else instance.total_blocks,
        exclude_not_available=True,
    )

    if not offers and should_retry:
        instance.last_retry_at = get_current_datetime()
        logger.debug(
            "No offers for instance %s. Next retry",
            instance.name,
            extra={"instance_name": instance.name},
        )
        return

    # Limit number of offers tried to prevent long-running processing
    # in case all offers fail.
    for backend, instance_offer in offers[: server_settings.MAX_OFFERS_TRIED]:
        if instance_offer.backend not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT:
            continue
        compute = backend.compute()
        assert isinstance(compute, ComputeWithCreateInstanceSupport)
        instance_offer = _get_instance_offer_for_instance(instance_offer, instance)
        if (
            _is_fleet_master_instance(instance)
            and instance_offer.backend in BACKENDS_WITH_PLACEMENT_GROUPS_SUPPORT
            and instance.fleet
            and _is_cloud_cluster(instance.fleet)
        ):
            assert isinstance(compute, ComputeWithPlacementGroupSupport)
            placement_group_model = _find_suitable_placement_group(
                placement_groups=placement_group_models,
                instance_offer=instance_offer,
                compute=compute,
            )
            if placement_group_model is None:
                placement_group_model = await _create_placement_group(
                    fleet_model=instance.fleet,
                    master_instance_offer=instance_offer,
                    compute=compute,
                )
                if placement_group_model is None:  # error occurred
                    continue
                session.add(placement_group_model)
                await session.flush()
                placement_group_models.append(placement_group_model)
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
                (
                    placement_group_model_to_placement_group(placement_group_model)
                    if placement_group_model
                    else None
                ),
            )
        except BackendError as e:
            logger.warning(
                "%s launch in %s/%s failed: %s",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
                repr(e),
                extra={"instance_name": instance.name},
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

        instance.status = InstanceStatus.PROVISIONING
        instance.backend = backend.TYPE
        instance.region = instance_offer.region
        instance.price = instance_offer.price
        instance.instance_configuration = instance_configuration.json()
        instance.job_provisioning_data = job_provisioning_data.json()
        instance.offer = instance_offer.json()
        instance.total_blocks = instance_offer.total_blocks
        instance.started_at = get_current_datetime()
        instance.last_retry_at = get_current_datetime()

        logger.info(
            "Created instance %s",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": InstanceStatus.PROVISIONING.value,
            },
        )
        if instance.fleet_id and _is_fleet_master_instance(instance):
            # Clean up placement groups that did not end up being used
            await schedule_fleet_placement_groups_deletion(
                session=session,
                fleet_id=instance.fleet_id,
                except_placement_group_ids=(
                    [placement_group_model.id] if placement_group_model is not None else []
                ),
            )
        return

    instance.last_retry_at = get_current_datetime()

    if not should_retry:
        _mark_terminated(instance, "All offers failed" if offers else "No offers found")
        if (
            instance.fleet
            and _is_fleet_master_instance(instance)
            and _is_cloud_cluster(instance.fleet)
        ):
            # Do not attempt to deploy other instances, as they won't determine the correct cluster
            # backend, region, and placement group without a successfully deployed master instance
            for sibling_instance in instance.fleet.instances:
                if sibling_instance.id == instance.id:
                    continue
                _mark_terminated(sibling_instance, "Master instance failed to start")


def _mark_terminated(instance: InstanceModel, termination_reason: str) -> None:
    instance.status = InstanceStatus.TERMINATED
    instance.termination_reason = termination_reason
    logger.info(
        "Terminated instance %s: %s",
        instance.name,
        instance.termination_reason,
        extra={
            "instance_name": instance.name,
            "instance_status": InstanceStatus.TERMINATED.value,
        },
    )


async def _check_instance(session: AsyncSession, instance: InstanceModel) -> None:
    if (
        instance.status == InstanceStatus.BUSY
        and instance.jobs
        and all(job.status.is_finished() for job in instance.jobs)
    ):
        # A busy instance could have no active jobs due to this bug: https://github.com/dstackai/dstack/issues/2068
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Instance job finished"
        logger.info(
            "Detected busy instance %s with finished job. Marked as TERMINATING",
            instance.name,
            extra={
                "instance_name": instance.name,
                "instance_status": instance.status.value,
            },
        )
        return

    job_provisioning_data = get_or_error(get_instance_provisioning_data(instance))
    if job_provisioning_data.hostname is None:
        res = await session.execute(
            select(ProjectModel)
            .where(ProjectModel.id == instance.id)
            .options(joinedload(ProjectModel.backends))
        )
        project = res.scalar_one()
        await _wait_for_instance_provisioning_data(
            project=project,
            instance=instance,
            job_provisioning_data=job_provisioning_data,
        )
        return

    if not job_provisioning_data.dockerized:
        if instance.status == InstanceStatus.PROVISIONING:
            instance.status = InstanceStatus.BUSY
        return

    ssh_private_keys = get_instance_ssh_private_keys(instance)

    # May return False if fails to establish ssh connection
    health_status_response = await run_async(
        _instance_healthcheck,
        ssh_private_keys,
        job_provisioning_data,
        None,
    )
    if isinstance(health_status_response, bool) or health_status_response is None:
        health_status = HealthStatus(healthy=False, reason="SSH or tunnel error")
    else:
        health_status = health_status_response

    logger.debug(
        "Check instance %s status. shim health: %s",
        instance.name,
        health_status,
        extra={"instance_name": instance.name, "shim_health": health_status},
    )

    if health_status.healthy:
        instance.termination_deadline = None
        instance.health_status = None
        instance.unreachable = False

        if instance.status == InstanceStatus.PROVISIONING:
            instance.status = InstanceStatus.IDLE if not instance.jobs else InstanceStatus.BUSY
            logger.info(
                "Instance %s has switched to %s status",
                instance.name,
                instance.status.value,
                extra={
                    "instance_name": instance.name,
                    "instance_status": instance.status.value,
                },
            )
        return

    if instance.termination_deadline is None:
        instance.termination_deadline = get_current_datetime() + TERMINATION_DEADLINE_OFFSET

    instance.health_status = health_status.reason
    instance.unreachable = True

    if instance.status == InstanceStatus.PROVISIONING and instance.started_at is not None:
        provisioning_deadline = _get_provisioning_deadline(
            instance=instance,
            job_provisioning_data=job_provisioning_data,
        )
        if get_current_datetime() > provisioning_deadline:
            instance.status = InstanceStatus.TERMINATING
            logger.warning(
                "Instance %s has not started in time. Marked as TERMINATING",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATING.value,
                },
            )
    elif instance.status in (InstanceStatus.IDLE, InstanceStatus.BUSY):
        logger.warning(
            "Instance %s shim is not available",
            instance.name,
            extra={"instance_name": instance.name},
        )
        deadline = instance.termination_deadline
        if get_current_datetime() > deadline:
            instance.status = InstanceStatus.TERMINATING
            instance.termination_reason = "Termination deadline"
            logger.warning(
                "Instance %s shim waiting timeout. Marked as TERMINATING",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATING.value,
                },
            )


async def _wait_for_instance_provisioning_data(
    project: ProjectModel,
    instance: InstanceModel,
    job_provisioning_data: JobProvisioningData,
):
    logger.debug(
        "Waiting for instance %s to become running",
        instance.name,
    )
    provisioning_deadline = _get_provisioning_deadline(
        instance=instance,
        job_provisioning_data=job_provisioning_data,
    )
    if get_current_datetime() > provisioning_deadline:
        logger.warning(
            "Instance %s failed because instance has not become running in time", instance.name
        )
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Instance has not become running in time"
        return

    backend = await backends_services.get_project_backend_by_type(
        project=project,
        backend_type=job_provisioning_data.backend,
    )
    if backend is None:
        logger.warning(
            "Instance %s failed because instance's backend is not available",
            instance.name,
        )
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Backend not available"
        return
    try:
        await run_async(
            backend.compute().update_provisioning_data,
            job_provisioning_data,
            project.ssh_public_key,
            project.ssh_private_key,
        )
        instance.job_provisioning_data = job_provisioning_data.json()
    except ProvisioningError as e:
        logger.warning(
            "Error while waiting for instance %s to become running: %s",
            instance.name,
            repr(e),
        )
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Error while waiting for instance to become running"
    except Exception:
        logger.exception(
            "Got exception when updating instance %s provisioning data", instance.name
        )


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _instance_healthcheck(ports: Dict[int, int]) -> HealthStatus:
    shim_client = runner_client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    try:
        resp = shim_client.healthcheck(unmask_exeptions=True)
        if resp is None:
            return HealthStatus(healthy=False, reason="Unknown reason")
        return runner_client.health_response_to_health_status(resp)
    except requests.RequestException as e:
        return HealthStatus(healthy=False, reason=f"Can't request shim: {e}")
    except Exception as e:
        logger.exception("Unknown exception from shim.healthcheck: %s", e)
        return HealthStatus(
            healthy=False, reason=f"Unknown exception ({e.__class__.__name__}): {e}"
        )


async def _terminate(instance: InstanceModel) -> None:
    if (
        instance.last_termination_retry_at is not None
        and _next_termination_retry_at(instance) > get_current_datetime()
    ):
        return
    jpd = get_instance_provisioning_data(instance)
    if jpd is not None:
        if jpd.backend != BackendType.REMOTE:
            backend = await backends_services.get_project_backend_by_type(
                project=instance.project, backend_type=jpd.backend
            )
            if backend is None:
                logger.error(
                    "Failed to terminate instance %s. Backend %s not available.",
                    instance.name,
                    jpd.backend,
                )
            else:
                logger.debug("Terminating runner instance %s", jpd.hostname)
                try:
                    await run_async(
                        backend.compute().terminate_instance,
                        jpd.instance_id,
                        jpd.region,
                        jpd.backend_data,
                    )
                except Exception as e:
                    if instance.first_termination_retry_at is None:
                        instance.first_termination_retry_at = get_current_datetime()
                    instance.last_termination_retry_at = get_current_datetime()
                    if _next_termination_retry_at(instance) < _get_termination_deadline(instance):
                        if isinstance(e, NotYetTerminated):
                            logger.debug(
                                "Instance %s termination in progress: %s", instance.name, e
                            )
                        else:
                            logger.warning(
                                "Failed to terminate instance %s. Will retry. Error: %r",
                                instance.name,
                                e,
                                exc_info=not isinstance(e, BackendError),
                            )
                        return
                    logger.error(
                        "Failed all attempts to terminate instance %s."
                        " Please terminate the instance manually to avoid unexpected charges."
                        " Error: %r",
                        instance.name,
                        e,
                        exc_info=not isinstance(e, BackendError),
                    )

    instance.deleted = True
    instance.deleted_at = get_current_datetime()
    instance.finished_at = get_current_datetime()
    instance.status = InstanceStatus.TERMINATED
    logger.info(
        "Instance %s terminated",
        instance.name,
        extra={
            "instance_name": instance.name,
            "instance_status": InstanceStatus.TERMINATED.value,
        },
    )


def _next_termination_retry_at(instance: InstanceModel) -> datetime.datetime:
    assert instance.last_termination_retry_at is not None
    return instance.last_termination_retry_at + TERMINATION_RETRY_TIMEOUT


def _get_termination_deadline(instance: InstanceModel) -> datetime.datetime:
    assert instance.first_termination_retry_at is not None
    return instance.first_termination_retry_at + TERMINATION_RETRY_MAX_DURATION


def _need_to_wait_fleet_provisioning(instance: InstanceModel) -> bool:
    # Cluster cloud instances should wait for the first fleet instance to be provisioned
    # so that they are provisioned in the same backend/region
    if instance.fleet is None:
        return False
    if (
        _is_fleet_master_instance(instance)
        or instance.fleet.instances[0].job_provisioning_data is not None
        or instance.fleet.instances[0].status == InstanceStatus.TERMINATED
    ):
        return False
    return _is_cloud_cluster(instance.fleet)


def _is_fleet_master_instance(instance: InstanceModel) -> bool:
    return instance.fleet is not None and instance.id == instance.fleet.instances[0].id


def _is_cloud_cluster(fleet_model: FleetModel) -> bool:
    fleet = fleet_model_to_fleet(fleet_model)
    return (
        fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER
        and fleet.spec.configuration.ssh_config is None
    )


def _get_instance_offer_for_instance(
    instance_offer: InstanceOfferWithAvailability,
    instance: InstanceModel,
) -> InstanceOfferWithAvailability:
    if instance.fleet is None:
        return instance_offer

    fleet = fleet_model_to_fleet(instance.fleet)
    master_instance = instance.fleet.instances[0]
    master_job_provisioning_data = get_instance_provisioning_data(master_instance)
    instance_offer = instance_offer.copy()
    if (
        fleet.spec.configuration.placement == InstanceGroupPlacement.CLUSTER
        and master_job_provisioning_data is not None
        and master_job_provisioning_data.availability_zone is not None
    ):
        if instance_offer.availability_zones is None:
            instance_offer.availability_zones = [master_job_provisioning_data.availability_zone]
        instance_offer.availability_zones = [
            z
            for z in instance_offer.availability_zones
            if z == master_job_provisioning_data.availability_zone
        ]
    return instance_offer


def _find_suitable_placement_group(
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


async def _create_placement_group(
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


def _get_instance_idle_duration(instance: InstanceModel) -> datetime.timedelta:
    last_time = instance.created_at
    if instance.last_job_processed_at is not None:
        last_time = instance.last_job_processed_at
    return get_current_datetime() - last_time


def _get_retry_duration_deadline(instance: InstanceModel, retry: Retry) -> datetime.datetime:
    return instance.created_at + timedelta(seconds=retry.duration)


def _get_provisioning_deadline(
    instance: InstanceModel,
    job_provisioning_data: JobProvisioningData,
) -> datetime.datetime:
    assert instance.started_at is not None
    timeout_interval = get_provisioning_timeout(
        backend_type=job_provisioning_data.get_base_backend(),
        instance_type_name=job_provisioning_data.instance_type.name,
    )
    return instance.started_at + timeout_interval


def _ssh_keys_to_pkeys(ssh_keys: list[SSHKey]) -> list[PKey]:
    return [pkey_from_str(sk.private) for sk in ssh_keys if sk.private is not None]
