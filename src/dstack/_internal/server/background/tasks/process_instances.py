import datetime
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Optional, Union
from uuid import UUID

import requests
from pydantic import ValidationError, parse_raw_as
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import (
    InstanceConfiguration,
    InstanceRuntime,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.profiles import Profile, TerminationPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, Requirements
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.jobs import (
    PROCESSING_POOL_IDS,
    PROCESSING_POOL_LOCK,
    terminate_job_provisioning_data_instance,
)
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.runs import get_create_instance_offers
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)

TERMINATION_DEADLINE_OFFSET = timedelta(minutes=20)

# Terminate instance if the instance has not provisioning within 10 minutes
PROVISIONING_TIMEOUT_SECONDS = 10 * 60  # 10 minutes in seconds


@dataclass
class HealthStatus:
    healthy: bool
    reason: str

    def __str__(self) -> str:
        return self.reason


logger = get_logger(__name__)


async def process_instances() -> None:
    async with get_session_ctx() as session:
        async with PROCESSING_POOL_LOCK:
            res = await session.scalars(
                select(InstanceModel).where(
                    InstanceModel.status.in_(
                        [
                            InstanceStatus.PROVISIONING,
                            InstanceStatus.TERMINATING,
                            InstanceStatus.IDLE,
                            InstanceStatus.BUSY,
                            InstanceStatus.PENDING,
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
            if instance.status == InstanceStatus.PENDING:
                await create_instance(instance.id)
            if instance.status in (
                InstanceStatus.PROVISIONING,
                InstanceStatus.IDLE,
                InstanceStatus.BUSY,
            ):
                await check_shim(instance.id)
            if instance.status == InstanceStatus.TERMINATING:
                await terminate(instance.id)
    finally:
        PROCESSING_POOL_IDS.difference_update(i.id for i in instances)


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
            retry_duration_deadline = instance.created_at.replace(
                tzinfo=datetime.timezone.utc
            ) + timedelta(seconds=instance.retry_policy_duration)
            if retry_duration_deadline < get_current_datetime():
                instance.status = InstanceStatus.TERMINATED
                instance.deleted = True
                instance.deleted_at = get_current_datetime()
                instance.termination_reason = "The retry's duration expired"
                await session.commit()
                logger.debug("The retry's duration expired. Terminate instance %s", instance.name)
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
            logger.debug(
                "Empty profile, requirements or instance_configuration. Terminate instance: %s",
                instance.name,
            )
            return

        try:
            profile = Profile.parse_raw(instance.profile)
            requirements = Requirements.parse_raw(instance.requirements)
            instance_configuration = InstanceConfiguration.parse_raw(
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
            logger.debug(
                "Error to parse profile, requirements or instance_configuration. Terminate instance: %s",
                instance.name,
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
            logger.debug("No offers for %s. Next retry", instance.name)
            return

        for backend, instance_offer in offers:
            # cannot create an instance in vastai/k8s. skip
            if instance_offer.instance_runtime == InstanceRuntime.RUNNER:
                continue
            logger.debug(
                "trying %s in %s/%s for $%0.4f per hour",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
                instance_offer.price,
            )
            try:
                launched_instance_info: LaunchedInstanceInfo = await run_async(
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
                )
                continue
            except NotImplementedError:
                # skip a backend without create_instance support, continue with next backend and offer
                continue
            job_provisioning_data = JobProvisioningData(
                backend=backend.TYPE,
                instance_type=instance_offer.instance,
                instance_id=launched_instance_info.instance_id,
                hostname=launched_instance_info.ip_address,
                region=launched_instance_info.region,
                price=instance_offer.price,
                username=launched_instance_info.username,
                ssh_port=launched_instance_info.ssh_port,
                dockerized=launched_instance_info.dockerized,
                backend_data=launched_instance_info.backend_data,
                ssh_proxy=None,
            )

            instance.status = InstanceStatus.PROVISIONING
            instance.backend = backend.TYPE
            instance.region = instance_offer.region
            instance.price = instance_offer.price
            instance.job_provisioning_data = job_provisioning_data.json()
            instance.offer = instance_offer.json()
            instance.started_at = get_current_datetime()
            instance.last_retry_at = get_current_datetime()

            await session.commit()
            logger.info("Created instance %s", instance.name)

            return

        instance.last_retry_at = get_current_datetime()

        if not instance.retry_policy:
            instance.status = InstanceStatus.TERMINATED
            instance.deleted = True
            instance.deleted_at = get_current_datetime()
            instance.termination_reason = "There were no offers found"
            logger.info("There were no offers found. Terminated instance %s", instance.name)

        await session.commit()


async def check_shim(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()
        job_provisioning_data = parse_raw_as(JobProvisioningData, instance.job_provisioning_data)

        # skip check vastai/k8s
        if not job_provisioning_data.dockerized:
            return

        ssh_private_key = instance.project.ssh_private_key
        instance_health: Union[Optional[HealthStatus], bool] = instance_healthcheck(
            ssh_private_key, job_provisioning_data
        )
        if isinstance(instance_health, bool) or instance_health is None:
            health = HealthStatus(healthy=False, reason="SSH or tunnel error")
        else:
            health = instance_health

        if health.healthy:
            logger.debug("check instance %s status: shim health is OK", instance.name)
            instance.termination_deadline = None
            instance.health_status = None

            if instance.status == InstanceStatus.PROVISIONING:
                instance.status = (
                    InstanceStatus.IDLE if instance.job_id is None else InstanceStatus.BUSY
                )
                await session.commit()
        else:
            logger.debug("check instance %s status: shim health: %s", instance.name, health)

            if instance.termination_deadline is None:
                instance.termination_deadline = (
                    get_current_datetime() + TERMINATION_DEADLINE_OFFSET
                )
            instance.health_status = health.reason

            if instance.status in (InstanceStatus.IDLE, InstanceStatus.BUSY):
                logger.warning("instance %s shim is not available", instance.name)
                deadline = instance.termination_deadline.replace(tzinfo=datetime.timezone.utc)
                if get_current_datetime() > deadline:
                    instance.status = InstanceStatus.TERMINATING
                    instance.termination_reason = "Termination deadline"
                    logger.warning("mark instance %s as TERMINATED", instance.name)

            if instance.status == InstanceStatus.PROVISIONING and instance.started_at is not None:
                provisioning_time_threshold = instance.started_at.replace(
                    tzinfo=datetime.timezone.utc
                ) + timedelta(seconds=PROVISIONING_TIMEOUT_SECONDS)
                expire_provisioning = provisioning_time_threshold < get_current_datetime()
                if expire_provisioning:
                    instance.status = InstanceStatus.TERMINATING
                    logger.warning(
                        "The Instance %s can't start in %s seconds. Marked as TERMINATED",
                        instance.name,
                        PROVISIONING_TIMEOUT_SECONDS,
                    )

            await session.commit()


@runner_ssh_tunnel(ports=[client.REMOTE_SHIM_PORT], retries=1)
def instance_healthcheck(*, ports: Dict[int, int]) -> HealthStatus:
    shim_client = client.ShimClient(port=ports[client.REMOTE_SHIM_PORT])
    try:
        resp = shim_client.healthcheck(unmask_exeptions=True)

        if resp is None:
            return HealthStatus(healthy=False, reason="Unknown reason")

        if resp.service == "dstack-shim":
            return HealthStatus(healthy=True, reason="Service is OK")
        else:
            return HealthStatus(
                healthy=False,
                reason=f"Service name is {resp.service}, service version: {resp.version}",
            )
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

        jpd = parse_raw_as(JobProvisioningData, instance.job_provisioning_data)
        backends = await backends_services.get_project_backends(project=instance.project)
        backend = next((b for b in backends if b.TYPE == jpd.backend), None)
        if backend is None:
            raise ValueError(f"there is no backend {jpd.backend}")

        await run_async(
            backend.compute().terminate_instance, jpd.instance_id, jpd.region, jpd.backend_data
        )

        instance.deleted = True
        instance.deleted_at = get_current_datetime()
        instance.finished_at = get_current_datetime()
        instance.status = InstanceStatus.TERMINATED

        logger.info("instance %s terminated", instance.name)

        await session.commit()


async def terminate_idle_instance() -> None:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(InstanceModel)
            .where(
                InstanceModel.termination_policy == TerminationPolicy.DESTROY_AFTER_IDLE,
                InstanceModel.deleted == False,
                InstanceModel.job == None,  # noqa: E711
            )
            .options(joinedload(InstanceModel.project))
        )
        instances = res.scalars().all()

        for instance in instances:
            last_time = instance.created_at.replace(tzinfo=datetime.timezone.utc)
            if instance.last_job_processed_at is not None:
                last_time = instance.last_job_processed_at.replace(tzinfo=datetime.timezone.utc)

            idle_seconds = instance.termination_idle_time
            delta = datetime.timedelta(seconds=idle_seconds)

            current_time = get_current_datetime().replace(tzinfo=datetime.timezone.utc)

            if last_time + delta < current_time:
                jpd: JobProvisioningData = parse_raw_as(
                    JobProvisioningData, instance.job_provisioning_data
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
                    "instance %s terminated by termination policy: idle time %ss",
                    instance.name,
                    str(idle_time.seconds),
                )

        await session.commit()
