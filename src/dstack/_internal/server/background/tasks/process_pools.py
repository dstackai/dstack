import datetime
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Optional, Union
from uuid import UUID

import requests
from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData
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


async def process_pools() -> None:
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
        for inst in instances:
            if inst.status in (
                InstanceStatus.PROVISIONING,
                InstanceStatus.IDLE,
                InstanceStatus.BUSY,
            ):
                await check_shim(inst.id)
            if inst.status == InstanceStatus.TERMINATING:
                await terminate(inst.id)
    finally:
        PROCESSING_POOL_IDS.difference_update(i.id for i in instances)


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
