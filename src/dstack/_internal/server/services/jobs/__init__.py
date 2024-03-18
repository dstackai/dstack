import asyncio
import datetime
import itertools
import json
from datetime import timezone
from typing import Dict, Iterable, List, Optional, Tuple

import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.gateways as gateways
from dstack._internal.core.errors import ResourceNotFoundError, SSHError
from dstack._internal.core.models.backends.base import BackendType
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
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import get_runner_ports, runner_ssh_tunnel
from dstack._internal.server.utils.common import run_async, wait_to_lock
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


def get_jobs_from_run_spec(run_spec: RunSpec, replica_num: int) -> List[Job]:
    return [
        Job(job_spec=s, job_submissions=[])
        for s in get_job_specs_from_run_spec(run_spec, replica_num)
    ]


def get_job_specs_from_run_spec(run_spec: RunSpec, replica_num: int) -> List[JobSpec]:
    job_configurator = _get_job_configurator(run_spec)
    job_specs = job_configurator.get_job_specs(replica_num=replica_num)
    return job_specs


def job_model_to_job_submission(job_model: JobModel) -> JobSubmission:
    job_provisioning_data = None
    if job_model.job_provisioning_data is not None:
        job_provisioning_data = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
        # TODO remove after transitioning to computed fields
        job_provisioning_data.instance_type.resources.description = (
            job_provisioning_data.instance_type.resources.pretty_format()
        )
        if (
            job_provisioning_data.backend == BackendType.DSTACK
            and job_provisioning_data.backend_data is not None
        ):
            backend_data = json.loads(job_provisioning_data.backend_data)
            job_provisioning_data.backend = backend_data["base_backend"]
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


def find_job(jobs: List[Job], replica_num: int, job_num: int) -> Job:
    for job in jobs:
        if job.job_spec.replica_num == replica_num and job.job_spec.job_num == job_num:
            return job
    raise ResourceNotFoundError(
        f"Job with replica_num={replica_num} and job_num={job_num} not found"
    )


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
    try:
        await run_async(_stop_runner, job_model, project.ssh_private_key)
        delay_job_instance_termination(job_model)
    except SSHError:
        logger.debug("%s: failed to stop runner", fmt(job_model))


def _stop_runner(
    job_model: JobModel,
    server_ssh_private_key: str,
):
    jpd = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
    logger.debug("%s: stopping runner %s", fmt(job_model), jpd.hostname)
    ports = get_runner_ports()
    with ssh_tunnel.RunnerTunnel(
        hostname=jpd.hostname,
        ssh_port=jpd.ssh_port,
        user=jpd.username,
        ports=ports,
        id_rsa=server_ssh_private_key,
        ssh_proxy=jpd.ssh_proxy,
    ):
        runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
        runner_client.stop()


async def process_terminating_job(session: AsyncSession, job_model: JobModel):
    """
    Used by both process_terminating_jobs and process_terminating_run.
    Caller must acquire the lock on the job.
    """
    if (
        job_model.remove_at is not None
        and job_model.remove_at.replace(tzinfo=datetime.timezone.utc) > get_current_datetime()
    ):
        # it's too early to terminate the instance
        return

    res = await session.execute(
        sa.select(InstanceModel)
        .where(
            InstanceModel.project_id == job_model.project_id,
            InstanceModel.job_id == job_model.id,
        )
        .options(sa_orm.joinedload(InstanceModel.project))
    )
    instance: Optional[InstanceModel] = res.scalar()

    if instance is not None:
        await wait_to_lock(PROCESSING_POOL_LOCK, PROCESSING_POOL_IDS, instance.id)
        await session.refresh(instance)
        try:
            # there is an associated instance to empty
            jpd: Optional[JobProvisioningData] = None
            if job_model.job_provisioning_data is not None:
                jpd = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
                logger.debug("%s: stopping container", fmt(job_model))
                await stop_container(job_model, jpd, instance.project.ssh_private_key)

            if instance.status == InstanceStatus.BUSY:
                instance.status = InstanceStatus.IDLE
            elif instance.status != InstanceStatus.TERMINATED:
                # instance was PROVISIONING (specially for the job)
                # schedule for termination
                instance.status = InstanceStatus.TERMINATING

            if jpd is None or not jpd.dockerized:
                # do not reuse vastai/k8s instances
                instance.status = InstanceStatus.TERMINATING

            instance.job_id = None
            instance.last_job_processed_at = get_current_datetime()
            logger.info(
                "%s: instance '%s' has been released, new status is %s",
                fmt(job_model),
                instance.name,
                instance.status.name,
            )
            await gateways.unregister_replica(
                session, job_model
            )  # TODO(egor-s) ensure always runs
        finally:
            PROCESSING_POOL_IDS.remove(instance.id)

    if job_model.termination_reason is not None:
        job_model.status = job_termination_reason_to_status(job_model.termination_reason)
    else:
        job_model.status = JobStatus.FAILED
        logger.warning("%s: job termination reason is not set", fmt(job_model))
    logger.info(
        "%s: job status is %s, reason: %s",
        fmt(job_model),
        job_model.status.name,
        job_model.termination_reason.name,
    )


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
        logger.debug("%s: can't stop container, shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    # we force container deletion because the runner had time to gracefully stop the job
    shim_client.stop(force=True)


def group_jobs_by_replica_latest(jobs: List[JobModel]) -> Iterable[Tuple[int, List[JobModel]]]:
    """
    Args:
        jobs: unsorted list of jobs

    Yields:
        latest jobs in each replica (replica_num, jobs)
    """
    jobs = sorted(jobs, key=lambda j: (j.replica_num, j.job_num, j.submission_num))
    for replica_num, all_replica_jobs in itertools.groupby(jobs, key=lambda j: j.replica_num):
        replica_jobs: List[JobModel] = []
        for job_num, job_submissions in itertools.groupby(
            all_replica_jobs, key=lambda j: j.job_num
        ):
            # take only the latest submission
            # the latest `submission_num` doesn't have to be the same for all jobs
            *_, latest_job_submission = job_submissions
            replica_jobs.append(latest_job_submission)
        yield replica_num, replica_jobs
