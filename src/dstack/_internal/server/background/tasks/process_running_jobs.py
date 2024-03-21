from datetime import timedelta
from typing import Dict, Optional
from uuid import UUID

from pydantic import parse_raw_as
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.server.services.gateways as gateways
from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.core.models.repos import RemoteRepoCreds
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    Run,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    JobModel,
    ProjectModel,
    RepoModel,
    RunModel,
)
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    find_job,
    job_model_to_job_submission,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.repos import get_code_model, repo_model_to_repo_head
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.runs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    run_model_to_run,
)
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.interpolator import VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_running_jobs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK, RUNNING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_(
                        [JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING]
                    ),
                    JobModel.id.not_in(RUNNING_PROCESSING_JOBS_IDS),
                    JobModel.run_id.not_in(
                        PROCESSING_RUNS_IDS
                    ),  # runs processing has higher priority
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)  # TODO process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return

            RUNNING_PROCESSING_JOBS_IDS.add(job_model.id)

    try:
        await _process_job(job_id=job_model.id)
    finally:
        RUNNING_PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel).where(JobModel.id == job_id).options(joinedload(JobModel.instance))
        )
        job_model = res.scalar_one()
        res = await session.execute(
            select(RunModel)
            .where(RunModel.id == job_model.run_id)
            .options(joinedload(RunModel.project))
            .options(joinedload(RunModel.user))
            .options(joinedload(RunModel.repo))
        )
        run_model = res.scalar_one()
        repo_model = run_model.repo
        project = run_model.project
        run = run_model_to_run(run_model)
        job_submission = job_model_to_job_submission(job_model)
        job_provisioning_data = job_submission.job_provisioning_data
        job = find_job(run.jobs, job_model.replica_num, job_model.job_num)

        server_ssh_private_key = project.ssh_private_key
        secrets = {}  # TODO secrets
        repo_creds = repo_model_to_repo_head(repo_model, include_creds=True).repo_creds

        initial_status = job_model.status
        if (
            initial_status == JobStatus.PROVISIONING
        ):  # fails are acceptable until timeout is exceeded
            if job_provisioning_data.dockerized:
                logger.debug(
                    "%s: process provisioning job with shim, age=%s",
                    fmt(job_model),
                    job_submission.age,
                )
                success = await run_async(
                    _process_provisioning_with_shim,
                    server_ssh_private_key,
                    job_provisioning_data,
                    job_model,
                    secrets,
                    job.job_spec.registry_auth,
                )
            else:
                logger.debug(
                    "%s: process provisioning job without shim, age=%s",
                    fmt(job_model),
                    job_submission.age,
                )
                code = await _get_job_code(
                    session=session,
                    project=project,
                    repo=repo_model,
                    code_hash=run.run_spec.repo_code_hash,
                )
                success = await run_async(
                    _process_provisioning_no_shim,
                    server_ssh_private_key,
                    job_provisioning_data,
                    run,
                    job_model,
                    job,
                    code,
                    secrets,
                    repo_creds,
                )

            if not success:
                # check timeout
                if job_submission.age > _get_runner_timeout_interval(
                    job_provisioning_data.backend
                ):
                    logger.warning(
                        "%s: failed because runner has not become available in time, age=%s",
                        fmt(job_model),
                        job_submission.age,
                    )
                    job_model.status = JobStatus.TERMINATING
                    job_model.termination_reason = (
                        JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED
                    )
                    # instance will be emptied by process_terminating_jobs

        else:  # fails are not acceptable
            if initial_status == JobStatus.PULLING:
                logger.debug(
                    "%s: process pulling job with shim, age=%s", fmt(job_model), job_submission.age
                )
                code = await _get_job_code(
                    session=session,
                    project=project,
                    repo=repo_model,
                    code_hash=run.run_spec.repo_code_hash,
                )
                success = await run_async(
                    _process_pulling_with_shim,
                    server_ssh_private_key,
                    job_provisioning_data,
                    run,
                    job_model,
                    job,
                    code,
                    secrets,
                    repo_creds,
                )
            elif initial_status == JobStatus.RUNNING:
                logger.debug("%s: process running job, age=%s", fmt(job_model), job_submission.age)
                success = await run_async(
                    _process_running,
                    server_ssh_private_key,
                    job_provisioning_data,
                    run_model,
                    job_model,
                )

            if not success:  # kill the job
                logger.warning(
                    "%s: failed because runner is not available, age=%s",
                    fmt(job_model),
                    job_submission.age,
                )
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
                # job will be terminated and instance will be emptied by process_terminating_jobs

        if (
            initial_status != job_model.status
            and job_model.status == JobStatus.RUNNING
            and job_model.job_num == 0  # gateway connects only to the first node
            and run.run_spec.configuration.type == "service"
        ):
            try:
                await gateways.register_replica(session, run_model.gateway_id, run, job_model)
            except GatewayError as e:
                logger.warning(
                    "%s: failed to register service replica: %s, age=%s",
                    fmt(job_model),
                    e,
                    job_submission.age,
                )
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = JobTerminationReason.GATEWAY_ERROR

        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()


@runner_ssh_tunnel(ports=[client.REMOTE_RUNNER_PORT], retries=1)
def _process_provisioning_no_shim(
    run: Run,
    job_model: JobModel,
    job: Job,
    code: bytes,
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
    *,
    ports: Dict[int, int],
) -> bool:
    """
    Possible next states:
    - JobStatus.RUNNING if runner is available
    - JobStatus.TERMINATING if timeout is exceeded

    Returns:
        is successful
    """

    runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
    resp = runner_client.healthcheck()
    if resp is None:
        return False  # runner is not available yet
    _submit_job_to_runner(
        runner_client=runner_client,
        run=run,
        job_model=job_model,
        job=job,
        code=code,
        secrets=secrets,
        repo_credentials=repo_credentials,
    )
    return True


@runner_ssh_tunnel(ports=[client.REMOTE_SHIM_PORT], retries=1)
def _process_provisioning_with_shim(
    job_model: JobModel,
    secrets: Dict[str, str],
    registry_auth: Optional[RegistryAuth],
    *,
    ports: Dict[int, int],
) -> bool:
    """
    Possible next states:
    - JobStatus.PULLING if shim is available
    - JobStatus.TERMINATING if timeout is exceeded

    Returns:
        is successful
    """
    job_spec = parse_raw_as(JobSpec, job_model.job_spec_data)

    shim_client = client.ShimClient(port=ports[client.REMOTE_SHIM_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    if registry_auth is not None:
        logger.debug("%s: authenticating to the registry...", fmt(job_model))
        interpolate = VariablesInterpolator({"secrets": secrets}).interpolate
        shim_client.submit(
            username=interpolate(registry_auth.username),
            password=interpolate(registry_auth.password),
            image_name=job_spec.image_name,
            container_name=job_model.job_name,
            shm_size=job_spec.requirements.resources.shm_size,
        )
    else:
        shim_client.submit(
            username="",
            password="",
            image_name=job_spec.image_name,
            container_name=job_model.job_name,
            shm_size=job_spec.requirements.resources.shm_size,
        )

    job_model.status = JobStatus.PULLING
    logger.info("%s: now is %s", fmt(job_model), job_model.status.name)
    return True


@runner_ssh_tunnel(ports=[client.REMOTE_SHIM_PORT, client.REMOTE_RUNNER_PORT])
def _process_pulling_with_shim(
    run: Run,
    job_model: JobModel,
    job: Job,
    code: bytes,
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
    *,
    ports: Dict[int, int],
) -> bool:
    """
    Possible next states:
    - JobStatus.RUNNING if runner is available
    - JobStatus.TERMINATING if shim is not available

    Returns:
        is successful
    """
    shim_client = client.ShimClient(port=ports[client.REMOTE_SHIM_PORT])
    container_status = shim_client.pull()  # raises error if shim is down, causes retry

    runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
    resp = runner_client.healthcheck()
    if resp is None:
        if (
            container_status.state == "pending"
            and container_status.container_name == job_model.job_name
        ):
            logger.error(
                "The docker container of the job '%s' is not working: exit code: %s, error %s",
                job_model.job_name,
                container_status.exit_code,
                container_status.error,
            )
            logger.debug("runner healthcheck: %s", container_status.dict())
            return False
        return True  # runner is not available yet, but shim is alive (pulling)

    _submit_job_to_runner(
        runner_client=runner_client,
        run=run,
        job_model=job_model,
        job=job,
        code=code,
        secrets=secrets,
        repo_credentials=repo_credentials,
    )
    return True


@runner_ssh_tunnel(ports=[client.REMOTE_RUNNER_PORT])
def _process_running(
    run_model: RunModel,
    job_model: JobModel,
    *,
    ports: Dict[int, int],
) -> bool:
    """
    Possible next states:
    - JobStatus.TERMINATING if runner is not available
    - Any status received from runner

    Returns:
        is successful
    """
    runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
    timestamp = 0
    if job_model.runner_timestamp is not None:
        timestamp = job_model.runner_timestamp
    resp = runner_client.pull(timestamp)  # raises error if runner is down, causes retry
    job_model.runner_timestamp = resp.last_updated
    logs_services.write_logs(
        project=run_model.project,
        run_name=run_model.run_name,
        job_submission_id=job_model.id,
        runner_logs=resp.runner_logs,
        job_logs=resp.job_logs,
    )
    if len(resp.job_states) > 0:
        latest_status = resp.job_states[-1].state
        # TODO(egor-s): refactor dstack-runner to return compatible statuses and reasons
        if latest_status == JobStatus.DONE:
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.DONE_BY_RUNNER
            # let the CLI pull logs?
            # delay_job_instance_termination(job_model)
        elif latest_status in {JobStatus.FAILED, JobStatus.ABORTED, JobStatus.TERMINATED}:
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.CONTAINER_EXITED_WITH_ERROR
            # let the CLI pull logs?
            # delay_job_instance_termination(job_model)
        logger.info("%s: now is %s", fmt(job_model), job_model.status.name)
    return True


async def _get_job_code(
    session: AsyncSession, project: ProjectModel, repo: RepoModel, code_hash: str
) -> bytes:
    code_model = await get_code_model(session=session, repo=repo, code_hash=code_hash)
    if code_model is None:
        return b""
    storage = get_default_storage()
    if storage is None or code_model.blob is not None:
        return code_model.blob
    blob = await run_async(
        storage.get_code,
        project.name,
        repo.name,
        code_hash,
    )
    return blob


def _submit_job_to_runner(
    runner_client: client.RunnerClient,
    run: Run,
    job_model: JobModel,
    job: Job,
    code: bytes,
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
):
    logger.debug("%s: submitting job spec", fmt(job_model))
    logger.debug(
        "%s: repo credentials are %s",
        fmt(job_model),
        None if repo_credentials is None else repo_credentials.protocol.value,
    )
    runner_client.submit_job(
        run_spec=run.run_spec,
        job_spec=job.job_spec,
        secrets=secrets,
        repo_credentials=repo_credentials,
    )
    logger.debug("%s: uploading code", fmt(job_model))
    runner_client.upload_code(code)
    logger.debug("%s: starting job", fmt(job_model))
    runner_client.run_job()

    job_model.status = JobStatus.RUNNING
    # do not log here, because the runner will send a new status


def _get_runner_timeout_interval(backend_type: BackendType) -> timedelta:
    if backend_type == BackendType.LAMBDA:
        return timedelta(seconds=1200)
    if backend_type == BackendType.KUBERNETES:
        return timedelta(seconds=1200)
    return timedelta(seconds=600)
