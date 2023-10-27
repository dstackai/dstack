import asyncio
import socket
from datetime import timezone
from typing import Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.core.models.runs import (
    Job,
    JobProvisioningData,
    JobSpec,
    JobStatus,
    JobSubmission,
    RunSpec,
)
from dstack._internal.core.services.ssh import tunnel as ssh_tunnel
from dstack._internal.server.models import JobModel, ProjectModel
from dstack._internal.server.services.backends import get_project_backend_by_type
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator
from dstack._internal.server.services.jobs.configurators.dev import DevEnvironmentJobConfigurator
from dstack._internal.server.services.jobs.configurators.service import ServiceJobConfigurator
from dstack._internal.server.services.jobs.configurators.task import TaskJobConfigurator
from dstack._internal.server.services.runner import client
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# TODO Make locks per project
SUBMITTED_PROCESSING_JOBS_LOCK = asyncio.Lock()
SUBMITTED_PROCESSING_JOBS_IDS = set()

RUNNING_PROCESSING_JOBS_LOCK = asyncio.Lock()
RUNNING_PROCESSING_JOBS_IDS = set()

TERMINATING_PROCESSING_JOBS_LOCK = asyncio.Lock()
TERMINATING_PROCESSING_JOBS_IDS = set()


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
    return JobSubmission(
        id=job_model.id,
        submission_num=job_model.submission_num,
        submitted_at=job_model.submitted_at.replace(tzinfo=timezone.utc),
        status=job_model.status,
        error_code=job_model.error_code,
        job_provisioning_data=job_provisioning_data,
    )


async def stop_job(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
    new_status: JobStatus,
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
            return

        job_submission = job_model_to_job_submission(job_model)
        if job_model.status in (JobStatus.PENDING, JobStatus.SUBMITTED):
            if new_status == JobStatus.TERMINATING:
                # there is no instance, just mark as terminated
                new_status = JobStatus.TERMINATED
        elif new_status == JobStatus.TERMINATING and job_model.status == JobStatus.RUNNING:
            await run_async(
                _stop_runner,
                job_submission,
                project.ssh_private_key,
            )
        elif new_status == JobStatus.ABORTED or job_model.status in (
            JobStatus.PROVISIONING,
            JobStatus.PULLING,
        ):
            await terminate_job_submission_instance(
                project=project,
                job_submission=job_submission,
            )
        else:
            raise RuntimeError(
                f"Unexpected job status transition: {job_model.status} -> {new_status}"
            )
        await session.execute(
            update(JobModel)
            .where(JobModel.id == job_model.id)
            .values(status=new_status, last_processed_at=get_current_datetime())
        )


async def terminate_job_submission_instance(
    project: ProjectModel,
    job_submission: JobSubmission,
):
    backend = await get_project_backend_by_type(
        project=project,
        backend_type=job_submission.job_provisioning_data.backend,
    )
    logger.debug("Terminating runner instance %s", job_submission.job_provisioning_data.hostname)
    await run_async(
        backend.compute().terminate_instance,
        job_submission.job_provisioning_data.instance_id,
        job_submission.job_provisioning_data.region,
    )


def get_runner_ports(ports: Optional[List[int]] = None) -> Dict[int, int]:
    ports = ports or [client.REMOTE_RUNNER_PORT]
    sockets = []
    try:
        for port in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("localhost", 0))  # Bind to a free port provided by the host
            sockets.append((port, s))
        return {port: s.getsockname()[1] for port, s in sockets}
    finally:
        for _, s in sockets:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.close()


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


def _stop_runner(
    job_submission: JobSubmission,
    server_ssh_private_key: str,
):
    ports = get_runner_ports()
    with ssh_tunnel.RunnerTunnel(
        hostname=job_submission.job_provisioning_data.hostname,
        ssh_port=job_submission.job_provisioning_data.ssh_port,
        user=job_submission.job_provisioning_data.username,
        ports=ports,
        id_rsa=server_ssh_private_key,
    ):
        runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
        logger.debug("Stopping runner %s", job_submission.job_provisioning_data.hostname)
        runner_client.stop()
