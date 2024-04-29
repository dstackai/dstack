import asyncio
import datetime
import ipaddress
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from uuid import UUID

import requests
from paramiko.pkey import PKey
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from dstack._internal import settings
from dstack._internal.core.backends import BACKENDS_WITH_CREATE_INSTANCE_SUPPORT
from dstack._internal.core.backends.base.compute import (
    DSTACK_WORKING_DIR,
    get_dstack_runner_version,
    get_shim_env,
    get_shim_pre_start_commands,
)
from dstack._internal.core.backends.remote.provisioning import (
    get_host_info,
    get_paramiko_connection,
    get_shim_healthcheck,
    host_info_to_instance_type,
    run_pre_start_commands,
    run_shim_as_systemd_service,
    upload_envs,
)
from dstack._internal.core.errors import BackendError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    RemoteConnectionInfo,
)
from dstack._internal.core.models.profiles import Profile, TerminationPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, Requirements
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, ProjectModel
from dstack._internal.server.schemas.runner import HealthcheckResponse
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.jobs import (
    PROCESSING_POOL_IDS,
    PROCESSING_POOL_LOCK,
    terminate_job_provisioning_data_instance,
)
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.runner.client import HealthStatus
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.runs import get_create_instance_offers
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import (
    rsa_pkey_from_str,
)

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)

PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds


logger = get_logger(__name__)


async def process_instances() -> None:
    async with get_session_ctx() as session:
        async with PROCESSING_POOL_LOCK:
            res = await session.scalars(
                select(InstanceModel).where(
                    InstanceModel.status.in_(
                        [
                            InstanceStatus.PENDING,
                            InstanceStatus.PROVISIONING,
                            InstanceStatus.BUSY,
                            InstanceStatus.IDLE,
                            InstanceStatus.TERMINATING,
                        ]
                    ),
                    InstanceModel.id.not_in(PROCESSING_POOL_IDS),
                )
            )
            instances = res.all()
            if not instances:
                return

            PROCESSING_POOL_IDS.update(i.id for i in instances)

    try:
        for instance in instances:
            if (
                instance.status == InstanceStatus.PENDING
                and instance.remote_connection_info is not None
            ):
                await add_remote(instance.id)

            if instance.status == InstanceStatus.PENDING:
                await create_instance(instance.id)

            if instance.status in (
                InstanceStatus.PROVISIONING,
                InstanceStatus.IDLE,
                InstanceStatus.BUSY,
            ):
                await check_instance(instance.id)

            if instance.status == InstanceStatus.TERMINATING:
                await terminate(instance.id)
    finally:
        PROCESSING_POOL_IDS.difference_update(i.id for i in instances)


def deploy_instance(
    remote_details: RemoteConnectionInfo, pkeys: List[PKey]
) -> Tuple[HealthStatus, Dict[str, Any]]:
    with get_paramiko_connection(
        remote_details.ssh_user, remote_details.host, remote_details.port, pkeys
    ) as client:
        logger.info(f"Connected to {remote_details.ssh_user} {remote_details.host}")

        runner_build = get_dstack_runner_version()

        # Execute pre start commands
        shim_pre_start_commands = get_shim_pre_start_commands(runner_build)
        run_pre_start_commands(
            client,
            shim_pre_start_commands,
            authorized_keys=[pk.public.strip() for pk in remote_details.ssh_keys],
        )
        logger.debug("The script for installing dstack has been executed")

        # Upload envs
        shim_envs = get_shim_env(
            runner_build, authorized_keys=[sk.public for sk in remote_details.ssh_keys]
        )
        upload_envs(client, DSTACK_WORKING_DIR, shim_envs)
        logger.debug("The dstack-shim environemnt variables has been installed")

        # Run dstack-shim as a systemd service
        run_shim_as_systemd_service(
            client=client,
            working_dir=DSTACK_WORKING_DIR,
            dev=settings.DSTACK_VERSION is None,
        )

        # Get host info
        host_info = get_host_info(client, DSTACK_WORKING_DIR)
        logger.debug("Received a host_info %s", host_info)

        raw_health = get_shim_healthcheck(client)
        try:
            health_response = HealthcheckResponse.__response__.parse_raw(raw_health)
        except ValueError as e:
            raise ProvisioningError("Cannot read HealthcheckResponse") from e
        health = runner_client.health_response_to_health_status(health_response)

        return health, host_info


async def add_remote(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()

        if instance.status == InstanceStatus.PENDING:
            instance.status = InstanceStatus.PROVISIONING
            await session.commit()

        retry_duration_deadline = instance.created_at.replace(
            tzinfo=datetime.timezone.utc
        ) + timedelta(seconds=PROVISIONING_TIMEOUT_SECONDS)
        if retry_duration_deadline < get_current_datetime():
            instance.status = InstanceStatus.TERMINATED
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
            instance.termination_reason = "The proivisioning timeout expired"
            await session.commit()
            logger.warning(
                "Failed to start the instance in %s seconds. Terminate instance %s",
                PROVISIONING_TIMEOUT_SECONDS,
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )
            return

        try:
            remote_details = RemoteConnectionInfo.parse_raw(
                cast(str, instance.remote_connection_info)
            )

            # Prepare connection key
            pkeys = [
                rsa_pkey_from_str(sk.private)
                for sk in remote_details.ssh_keys
                if sk.private is not None
            ]
            if not pkeys:
                logger.error("There are no ssh private key")
                raise ProvisioningError("The SSH private key is not provided")

            try:
                future = asyncio.get_running_loop().run_in_executor(
                    None, deploy_instance, remote_details, pkeys
                )
                deploy_timeout = 20 * 60  # 20 minutes
                result = await asyncio.wait_for(future, timeout=deploy_timeout)
                health, host_info = result
            except (asyncio.TimeoutError, TimeoutError) as e:
                raise ProvisioningError() from e
            except Exception as e:
                logger.debug("deploy_instance raise an error: %s", e)
                raise ProvisioningError() from e
            else:
                logger.info(
                    "The instance %s (%s) was successfully added",
                    instance.name,
                    remote_details.host,
                )

        except ProvisioningError as e:
            logger.warning("Provisioning could not be completed because of the error: %s", e)
            instance.status = InstanceStatus.PENDING
            instance.last_retry_at = get_current_datetime()
            await session.commit()
            return

        instance_type = host_info_to_instance_type(host_info)

        addresses = []
        for address in host_info.get("addresses", []):
            try:
                addresses.append(str(ipaddress.IPv4Address(address.rstrip("/32"))))
            except ipaddress.AddressValueError:
                continue
        internal_ip = addresses[0] if addresses else None

        jpd = JobProvisioningData(
            backend=BackendType.REMOTE,
            instance_type=instance_type,
            instance_id="instance_id",
            hostname=remote_details.host,
            region="remote",
            price=0,
            internal_ip=internal_ip,
            username=remote_details.ssh_user,
            ssh_port=22,
            dockerized=True,
            backend_data=None,
            ssh_proxy=None,
        )

        instance.status = InstanceStatus.IDLE if health else InstanceStatus.PROVISIONING
        instance.backend = BackendType.REMOTE

        instance.region = "remote"

        instance_offer = InstanceOfferWithAvailability(
            backend=BackendType.REMOTE,
            instance=instance_type,
            region="remote",
            price=0,
            availability=InstanceAvailability.AVAILABLE,
            instance_runtime=InstanceRuntime.SHIM,
        )

        instance.price = 0
        instance.offer = instance_offer.json()
        instance.job_provisioning_data = jpd.json()

        instance.started_at = get_current_datetime()
        instance.last_retry_at = get_current_datetime()

        await session.commit()


async def create_instance(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()

        if instance.retry_policy and instance.retry_policy_duration is not None:
            retry_duration_deadline = _get_retry_duration_deadline(instance)
            if get_current_datetime() > retry_duration_deadline:
                instance.status = InstanceStatus.TERMINATED
                instance.deleted = True
                instance.deleted_at = get_current_datetime()
                instance.termination_reason = "Retry duration expired"
                await session.commit()
                logger.warning(
                    "Retry duration expired. Terminate instance %s",
                    instance.name,
                    extra={
                        "instance_name": instance.name,
                        "instance_status": InstanceStatus.TERMINATED.value,
                    },
                )
                return

        if instance.last_retry_at is not None:
            last_retry = instance.last_retry_at.replace(tzinfo=datetime.timezone.utc)
            if get_current_datetime() < last_retry + timedelta(minutes=1):
                return

        if (
            instance.profile is None
            or instance.requirements is None
            or instance.instance_configuration is None
        ):
            instance.status = InstanceStatus.TERMINATED
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
            instance.termination_reason = "Empty profile, requirements or instance_configuration"
            instance.last_retry_at = get_current_datetime()
            await session.commit()
            logger.warning(
                "Empty profile, requirements or instance_configuration. Terminate instance: %s",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )
            return

        try:
            profile = Profile.__response__.parse_raw(instance.profile)
            requirements = Requirements.__response__.parse_raw(instance.requirements)
            instance_configuration = InstanceConfiguration.__response__.parse_raw(
                instance.instance_configuration
            )
        except ValidationError as e:
            instance.status = InstanceStatus.TERMINATED
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
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
            await session.commit()
            return

        offers = await get_create_instance_offers(
            project=instance.project,
            profile=profile,
            requirements=requirements,
            exclude_not_available=True,
        )

        if not offers and instance.retry_policy:
            instance.last_retry_at = get_current_datetime()
            await session.commit()
            logger.debug(
                "No offers for instance %s. Next retry",
                instance.name,
                extra={"instance_name": instance.name},
            )
            return

        for backend, instance_offer in offers:
            if instance_offer.backend not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT:
                continue
            logger.debug(
                "Trying %s in %s/%s for $%0.4f per hour",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
                instance_offer.price,
            )
            try:
                job_provisioning_data = await run_async(
                    backend.compute().create_instance,
                    instance_offer,
                    instance_configuration,
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
            except NotImplementedError:
                # skip a backend without create_instance support, continue with next backend and offer
                continue

            instance.status = InstanceStatus.PROVISIONING
            instance.backend = backend.TYPE
            instance.region = instance_offer.region
            instance.price = instance_offer.price
            instance.job_provisioning_data = job_provisioning_data.json()
            instance.offer = instance_offer.json()
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
            await session.commit()
            return

        instance.last_retry_at = get_current_datetime()

        if not instance.retry_policy:
            instance.status = InstanceStatus.TERMINATED
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
            instance.termination_reason = "No offers found"
            logger.info(
                "No offers found. Terminated instance %s",
                instance.name,
                extra={
                    "instance_name": instance.name,
                    "instance_status": InstanceStatus.TERMINATED.value,
                },
            )

        await session.commit()


async def check_instance(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()

        job_provisioning_data = JobProvisioningData.__response__.parse_raw(
            instance.job_provisioning_data
        )

        if job_provisioning_data.hostname is None:
            await wait_for_instance_provisioning_data(
                project=instance.project,
                instance=instance,
                job_provisioning_data=job_provisioning_data,
            )
            await session.commit()
            return

        if not job_provisioning_data.dockerized:
            return

        ssh_private_key = instance.project.ssh_private_key
        if instance.remote_connection_info is not None:
            remote_conn_info: RemoteConnectionInfo = RemoteConnectionInfo.__response__.parse_raw(
                instance.remote_connection_info
            )
            ssh_private_key = remote_conn_info.ssh_keys[0].private

        instance_health: Union[Optional[HealthStatus], bool] = await run_async(
            instance_healthcheck, ssh_private_key, job_provisioning_data
        )
        if isinstance(instance_health, bool) or instance_health is None:
            health = HealthStatus(healthy=False, reason="SSH or tunnel error")
        else:
            health = instance_health

        logger.debug(
            "Check instance %s status. shim health: %s",
            instance.name,
            health,
            extra={"instance_name": instance.name, "shim_health": health},
        )

        if health:
            instance.termination_deadline = None
            # FIXME why health_status is None?
            instance.health_status = None

            if instance.status == InstanceStatus.PROVISIONING:
                instance.status = (
                    InstanceStatus.IDLE if instance.job_id is None else InstanceStatus.BUSY
                )
                logger.info(
                    "Instance %s has switched to %s status",
                    instance.name,
                    instance.status.value,
                    extra={
                        "instance_name": instance.name,
                        "instance_status": instance.status.value,
                    },
                )
            await session.commit()
            return

        if instance.termination_deadline is None:
            instance.termination_deadline = get_current_datetime() + TERMINATION_DEADLINE_OFFSET

        instance.health_status = health.reason

        if instance.status == InstanceStatus.PROVISIONING and instance.started_at is not None:
            provisioning_deadline = _get_provisioning_deadline(instance)
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
            deadline = instance.termination_deadline.replace(tzinfo=datetime.timezone.utc)
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

        await session.commit()


async def wait_for_instance_provisioning_data(
    project: ProjectModel,
    instance: InstanceModel,
    job_provisioning_data: JobProvisioningData,
):
    logger.debug(
        "Waiting for instance %s to become running",
        instance.name,
    )
    provisioning_deadline = _get_provisioning_deadline(instance)
    if get_current_datetime() > provisioning_deadline:
        logger.warning(
            "Instance %s failed because instance has not become running in time", instance.name
        )
        instance.status = InstanceStatus.TERMINATING
        instance.termination_reason = "Instance has not become running in time"
    else:
        backend = await backends_services.get_project_backend_by_type(
            project=project,
            backend_type=job_provisioning_data.backend,
        )
        if backend is None:
            logger.warning(
                "Cannot stop instance %s because instance's backend is not configured",
                instance.name,
            )
        else:
            try:
                backend.compute().update_provisioning_data(job_provisioning_data)
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


@runner_ssh_tunnel(ports=[runner_client.REMOTE_SHIM_PORT], retries=1)
def instance_healthcheck(*, ports: Dict[int, int]) -> HealthStatus:
    shim_client = runner_client.ShimClient(port=ports[runner_client.REMOTE_SHIM_PORT])
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


async def terminate(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()

        if instance.job_provisioning_data is not None:
            jpd = JobProvisioningData.__response__.parse_raw(instance.job_provisioning_data)
            if jpd.backend != BackendType.REMOTE:
                backends = await backends_services.get_project_backends(project=instance.project)
                backend = next((b for b in backends if b.TYPE == jpd.backend), None)
                if backend is None:
                    raise ValueError(f"there is no backend {jpd.backend}")

                await run_async(
                    backend.compute().terminate_instance,
                    jpd.instance_id,
                    jpd.region,
                    jpd.backend_data,
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

        await session.commit()


async def terminate_idle_instances() -> None:
    async with get_session_ctx() as session:
        async with PROCESSING_POOL_LOCK:
            res = await session.execute(
                select(InstanceModel)
                .where(
                    InstanceModel.termination_policy == TerminationPolicy.DESTROY_AFTER_IDLE,
                    InstanceModel.deleted == False,
                    InstanceModel.job == None,  # noqa: E711
                    InstanceModel.status == InstanceStatus.IDLE,
                )
                .options(joinedload(InstanceModel.project))
            )
            instances = res.scalars().all()

            for instance in instances:
                last_time = instance.created_at.replace(tzinfo=datetime.timezone.utc)
                if instance.last_job_processed_at is not None:
                    last_time = instance.last_job_processed_at.replace(
                        tzinfo=datetime.timezone.utc
                    )

                idle_seconds = instance.termination_idle_time
                delta = datetime.timedelta(seconds=idle_seconds)

                current_time = get_current_datetime()
                if last_time + delta < current_time:
                    jpd = JobProvisioningData.__response__.parse_raw(
                        instance.job_provisioning_data
                    )
                    await terminate_job_provisioning_data_instance(
                        project=instance.project, job_provisioning_data=jpd
                    )
                    instance.deleted = True
                    instance.deleted_at = get_current_datetime()
                    instance.finished_at = get_current_datetime()
                    instance.status = InstanceStatus.TERMINATED
                    instance.termination_reason = "Idle timeout"
                    idle_time = current_time - last_time
                    logger.info(
                        "Instance %s terminated by termination policy: idle time %ss",
                        instance.name,
                        str(idle_time.seconds),
                        extra={
                            "instance_name": instance.name,
                            "instance_status": InstanceStatus.TERMINATED.value,
                        },
                    )
            await session.commit()


def _get_retry_duration_deadline(instance: InstanceModel) -> datetime.datetime:
    return instance.created_at.replace(tzinfo=datetime.timezone.utc) + timedelta(
        seconds=instance.retry_policy_duration
    )


def _get_provisioning_deadline(instance: InstanceModel) -> datetime.datetime:
    timeout_interval = _get_instance_timeout_interval(backend_type=instance.backend)
    return instance.started_at.replace(tzinfo=datetime.timezone.utc) + timeout_interval


def _get_instance_timeout_interval(backend_type: BackendType) -> timedelta:
    if backend_type == BackendType.RUNPOD:
        return timedelta(seconds=1200)
    return timedelta(seconds=600)
