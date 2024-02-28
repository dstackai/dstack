import asyncio
import datetime
import uuid
from datetime import timezone
from typing import Dict, List, Optional, Set

import sqlalchemy as sa
import sqlalchemy.orm
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import SSHError
from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.core.models.runs import (
    InstanceStatus,
    Job,
    JobProvisioningData,
    JobSpec,
    JobStatus,
    JobSubmission,
    JobTerminationReason,
    RunSpec,
)
from dstack._internal.core.services.ssh import tunnel as ssh_tunnel
from dstack._internal.server.models import InstanceModel, JobModel, ProjectModel
from dstack._internal.server.services.backends import get_project_backend_by_type
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator
from dstack._internal.server.services.jobs.configurators.dev import DevEnvironmentJobConfigurator
from dstack._internal.server.services.jobs.configurators.service import ServiceJobConfigurator
from dstack._internal.server.services.jobs.configurators.task import TaskJobConfigurator
from dstack._internal.server.services.logging import job_log
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import get_runner_ports, runner_ssh_tunnel
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# TODO Make locks per project
SUBMITTED_PROCESSING_JOBS_LOCK = asyncio.Lock()
SUBMITTED_PROCESSING_JOBS_IDS = set()

RUNNING_PROCESSING_JOBS_LOCK = asyncio.Lock()
RUNNING_PROCESSING_JOBS_IDS = set()

PROCESSING_POOL_LOCK = asyncio.Lock()
PROCESSING_POOL_IDS = set()

TERMINATING_PROCESSING_JOBS_LOCK = asyncio.Lock()
TERMINATING_PROCESSING_JOBS_IDS = set()

PROCESSING_RUNS_LOCK = asyncio.Lock()
PROCESSING_RUNS_IDS: Set[uuid.UUID] = set()


def get_jobs_from_run_spec(run_spec: RunSpec) -> List[Job]:
    job_configurator = _get_job_configurator(run_spec)
    job_specs = job_configurator.get_job_specs()
    return [Job(job_spec=s, job_submissions=[]) for s in job_specs]


def get_job_specs_from_run_spec(run_spec: RunSpec) -> List[JobSpec]:
    job_configurator = _get_job_configurator(run_spec)
    job_specs = job_configurator.get_job_specs()
    return job_specs


def job_model_to_job_submission(job_model: JobModel) -> JobSubmission:
    job_provisioning_data = None
    if job_model.job_provisioning_data is not None:
        job_provisioning_data = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
        # TODO remove after transitioning to computed fields
        job_provisioning_data.instance_type.resources.description = (
            job_provisioning_data.instance_type.resources.pretty_format()
        )
    finished_at = None
    if job_model.status.is_finished():
        finished_at = job_model.last_processed_at.replace(tzinfo=timezone.utc)
    return JobSubmission(
        id=job_model.id,
        submission_num=job_model.submission_num,
        submitted_at=job_model.submitted_at.replace(tzinfo=timezone.utc),
        finished_at=finished_at,
        status=job_model.status,
        termination_reason=job_model.termination_reason,
        job_provisioning_data=job_provisioning_data,
    )


async def stop_job(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
):
    if job_model.status.is_finished():
        return
    async with SUBMITTED_PROCESSING_JOBS_LOCK, RUNNING_PROCESSING_JOBS_LOCK, TERMINATING_PROCESSING_JOBS_LOCK:
        # If the job provisioning is in progress, we have to wait until it's done.
        # We can also consider returning an error when stopping a provisioning job.
        while (
            job_model.id in SUBMITTED_PROCESSING_JOBS_IDS
            or job_model.id in RUNNING_PROCESSING_JOBS_IDS
            or job_model.id in TERMINATING_PROCESSING_JOBS_IDS
        ):
            await asyncio.sleep(0.1)
        await session.refresh(job_model)
        if job_model.status.is_finished():
            # process_finished_jobs will process the job in the background
            return

        job_submission = job_model_to_job_submission(job_model)
        if job_model.status == JobStatus.RUNNING:
            try:
                await run_async(
                    _stop_runner, job_submission.job_provisioning_data, project.ssh_private_key
                )
                # delay termination for 15 seconds to allow the runner to stop gracefully
                delay_job_instance_termination(job_model)
            except SSHError:
                logger.debug(*job_log("failed to stop runner", job_model))
        # process_finished_jobs will terminate the instance in the background
        job_model.status = JobStatus.TERMINATED
        job_model.last_processed_at = get_current_datetime()
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_USER
        await session.commit()
        logger.info(*job_log("%s by user", job_model, job_model.status.value))


async def terminate_job_provisioning_data_instance(
    project: ProjectModel, job_provisioning_data: JobProvisioningData
):
    backend = await get_project_backend_by_type(
        project=project,
        backend_type=job_provisioning_data.backend,
    )
    logger.debug("Terminating runner instance %s", job_provisioning_data.hostname)
    await run_async(
        backend.compute().terminate_instance,
        job_provisioning_data.instance_id,
        job_provisioning_data.region,
        job_provisioning_data.backend_data,
    )


def delay_job_instance_termination(job_model: JobModel):
    job_model.remove_at = get_current_datetime() + datetime.timedelta(seconds=15)


def _get_job_configurator(run_spec: RunSpec) -> JobConfigurator:
    configuration_type = ConfigurationType(run_spec.configuration.type)
    configurator_class = _configuration_type_to_configurator_class_map[configuration_type]
    return configurator_class(run_spec)


_job_configurator_classes = [
    DevEnvironmentJobConfigurator,
    TaskJobConfigurator,
    ServiceJobConfigurator,
]

_configuration_type_to_configurator_class_map = {c.TYPE: c for c in _job_configurator_classes}


async def stop_runner(session: AsyncSession, job_model: JobModel):
    project = await session.get(ProjectModel, job_model.project_id)
    jpd = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
    try:
        await run_async(_stop_runner, jpd, project.ssh_private_key)
        delay_job_instance_termination(job_model)
    except SSHError:
        logger.debug(*job_log("failed to stop runner", job_model))


def _stop_runner(
    job_provisioning_data: JobProvisioningData,
    server_ssh_private_key: str,
):
    ports = get_runner_ports()
    with ssh_tunnel.RunnerTunnel(
        hostname=job_provisioning_data.hostname,
        ssh_port=job_provisioning_data.ssh_port,
        user=job_provisioning_data.username,
        ports=ports,
        id_rsa=server_ssh_private_key,
        ssh_proxy=job_provisioning_data.ssh_proxy,
    ):
        runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
        logger.debug("Stopping runner %s", job_provisioning_data.hostname)
        runner_client.stop()


async def process_terminating_job(session: AsyncSession, job_model: JobModel):
    """
    Used by both process_terminating_jobs and process_terminating_run.
    Caller must acquire the lock on the job.
    """
    if job_model.remove_at is not None and job_model.remove_at > get_current_datetime():
        # it's too early to terminate the instance
        return

    res = await session.execute(
        sa.select(InstanceModel)
        .where(
            InstanceModel.project_id == job_model.project_id,
            InstanceModel.job_id == job_model.id,
        )
        .options(sa.orm.joinedload(InstanceModel.project))
    )
    instance: Optional[InstanceModel] = res.one_or_none()

    if instance is not None:
        # there is an associated instance to empty
        jpd: Optional[JobProvisioningData] = None
        if job_model.job_provisioning_data is not None:
            jpd = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
            await stop_container(job_model, jpd, instance.project.ssh_private_key)

        if instance.status == InstanceStatus.BUSY:
            instance.status = InstanceStatus.READY
        elif instance.status != InstanceStatus.TERMINATED:
            # instance was CREATING or STARTING (specially for the job)
            # schedule for termination
            instance.status = InstanceStatus.TERMINATING

        if jpd is None or not jpd.dockerized:
            # do not reuse vastai/k8s instances
            instance.status = InstanceStatus.TERMINATING

        instance.job_id = None
        instance.last_job_processed_at = get_current_datetime()
        # TODO(egor-s): unregister service replica

    job_model.status = job_termination_reason_to_status(job_model.termination_reason)


def job_termination_reason_to_status(termination_reason: JobTerminationReason) -> JobStatus:
    mapping = {
        JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY: JobStatus.FAILED,
        JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY: JobStatus.FAILED,
        JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED: JobStatus.FAILED,
        JobTerminationReason.TERMINATED_BY_USER: JobStatus.TERMINATED,
        JobTerminationReason.GATEWAY_ERROR: JobStatus.FAILED,
        JobTerminationReason.SCALED_DOWN: JobStatus.TERMINATED,
        JobTerminationReason.DONE_BY_RUNNER: JobStatus.DONE,
        JobTerminationReason.ABORTED_BY_USER: JobStatus.ABORTED,
        JobTerminationReason.TERMINATED_BY_SERVER: JobStatus.TERMINATED,
        JobTerminationReason.CONTAINER_EXITED_WITH_ERROR: JobStatus.FAILED,
        JobTerminationReason.PORTS_BINDING_FAILED: JobStatus.FAILED,
    }
    return mapping[termination_reason]


async def stop_container(
    job_model: JobModel, job_provisioning_data: JobProvisioningData, ssh_private_key: str
):
    if job_provisioning_data.dockerized:
        # send a request to the shim to terminate the docker container
        # SSHError and RequestException are caught in the `runner_ssh_tunner` decorator
        await run_async(
            _shim_submit_stop,
            ssh_private_key,
            job_provisioning_data,
            job_model,
        )


@runner_ssh_tunnel(ports=[client.REMOTE_SHIM_PORT])
def _shim_submit_stop(job_model: JobModel, ports: Dict[int, int]):
    shim_client = client.ShimClient(port=ports[client.REMOTE_SHIM_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    shim_client.stop(force=False)


def fmt(job_model: JobModel) -> str:
    return f"({job_model.id.hex[:6]}){job_model.job_name}"
