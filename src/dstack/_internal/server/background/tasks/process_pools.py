import datetime
from datetime import timedelta
from typing import Dict
from uuid import UUID

from pydantic import parse_raw_as  # type: ignore[attr-defined]
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
from dstack._internal.utils.common import get_current_datetime, parse_pretty_duration
from dstack._internal.utils.logging import get_logger

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)

logger = get_logger(__name__)


async def process_pools() -> None:
    async with get_session_ctx() as session:
        async with PROCESSING_POOL_LOCK:
            res = await session.scalars(
                select(InstanceModel).where(
                    InstanceModel.status.in_(
                        [
                            InstanceStatus.CREATING,
                            InstanceStatus.STARTING,
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
        for inst in instances:
            if inst.status in (InstanceStatus.CREATING, InstanceStatus.STARTING):
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
        ssh_private_key = instance.project.ssh_private_key
        job_provisioning_data = parse_raw_as(JobProvisioningData, instance.job_provisioning_data)

        instance_health = instance_healthcheck(ssh_private_key, job_provisioning_data)

        logger.info("check instance %s status: %s", instance.name, instance_health)

        if instance_health:
            instance.status = InstanceStatus.READY
            await session.commit()
            return


@runner_ssh_tunnel(ports=[client.REMOTE_SHIM_PORT], retries=1)  # type: ignore[misc]
def instance_healthcheck(*, ports: Dict[int, int]) -> bool:
    shim_client = client.ShimClient(port=ports[client.REMOTE_SHIM_PORT])
    resp = shim_client.healthcheck()
    if resp is None:
        return False  # shim is not available yet
    return bool(resp.service == "dstack-shim")


async def terminate(instance_id: UUID) -> None:
    async with get_session_ctx() as session:
        instance = (
            await session.scalars(
                select(InstanceModel)
                .where(InstanceModel.id == instance_id)
                .options(joinedload(InstanceModel.project))
            )
        ).one()

        # TODO: need lock

        jpd = parse_raw_as(JobProvisioningData, instance.job_provisioning_data)
        BACKEND_TYPE = jpd.backend
        backends = await backends_services.get_project_backends(project=instance.project)
        backend = next((b for b in backends if b.TYPE in BACKEND_TYPE), None)
        if backend is None:
            raise ValueError(f"there is no backned {BACKEND_TYPE}")

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

        # TODO: need lock

        for instance in instances:
            if instance.last_job_processed_at is None:
                continue

            delta = datetime.timedelta(
                seconds=parse_pretty_duration(instance.termination_idle_time)
            )
            if instance.last_job_processed_at.replace(
                tzinfo=datetime.timezone.utc
            ) + delta < get_current_datetime().replace(tzinfo=datetime.timezone.utc):
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

                idle_time = get_current_datetime().replace(
                    tzinfo=datetime.timezone.utc
                ) - instance.last_job_processed_at.replace(tzinfo=datetime.timezone.utc)
                logger.info(
                    "instance %s terminated by termination policy: idle time %ss",
                    instance.name,
                    str(idle_time.seconds),
                )

        await session.commit()
