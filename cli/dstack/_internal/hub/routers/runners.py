import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from dstack._internal.core.build import BuildNotFoundError
from dstack._internal.core.error import NoGatewayError, NoMatchingInstanceError, SSHCommandError
from dstack._internal.core.instance import InstanceAvailability
from dstack._internal.core.job import ConfigurationType, Job, JobStatus
from dstack._internal.hub.repository.jobs import JobManager
from dstack._internal.hub.routers.util import (
    call_backend,
    error_detail,
    get_job_backend,
    get_project,
    get_run_backend,
)
from dstack._internal.hub.schemas import RunRunners, StopRunners
from dstack._internal.hub.security.permissions import ProjectMember
from dstack._internal.hub.services.common import get_backends, get_instance_candidates
from dstack._internal.hub.utils.gateway import setup_job_gateway
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(
    prefix="/api/project", tags=["runners"], dependencies=[Depends(ProjectMember())]
)


@router.post("/{project_name}/runners/run")
async def run(project_name: str, body: RunRunners):
    job = body.job
    project = await get_project(project_name=project_name)
    backends = await get_backends(project, selected_backends=job.backends)
    backends = [backend for _, backend in backends]

    start = datetime.datetime.now()
    candidates = await get_instance_candidates(backends, job, exclude_not_available=True)
    logger.debug(
        f"Found %d instance candidates in %s",
        len(candidates),
        str(datetime.datetime.now() - start),
    )

    try:
        if job.configuration_type == ConfigurationType.SERVICE:
            await setup_job_gateway(project, job)
        for backend, offer in candidates:
            logger.info(
                "Trying %s in %s/%s for $%0.4f per hour",
                offer.instance.instance_name,
                backend.name,
                offer.region,
                offer.price,
            )
            try:
                await call_backend(
                    backend.run_job,
                    job,
                    project.ssh_private_key,
                    offer,
                )
                return
            except NoMatchingInstanceError:
                continue
    except BuildNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(msg=BuildNotFoundError.message, code=BuildNotFoundError.code),
        )
    except (SSHCommandError, NoGatewayError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(msg=e.message, code=e.code),
        )
    if job.retry_active():
        job.status = JobStatus.PENDING
        await JobManager.create(project_name=project.name, job=job)
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail("Run failed due to no capacity.", code=NoMatchingInstanceError.code),
    )


@router.post("/{project_name}/runners/restart")
async def restart(project_name: str, job: Job):
    project = await get_project(project_name=project_name)
    _, backend = await get_run_backend(project, job.repo.repo_id, job.run_name)
    await call_backend(backend.restart_job, job)


@router.post("/{project_name}/runners/stop")
async def stop(project_name: str, body: StopRunners):
    project = await get_project(project_name=project_name)
    _, backend = await get_job_backend(project, body.repo_id, body.job_id)
    await call_backend(backend.stop_job, body.repo_id, body.job_id, body.terminate, body.abort)
