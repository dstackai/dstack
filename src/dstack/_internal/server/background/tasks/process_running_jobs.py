import time
from datetime import timedelta
from typing import Dict, Optional
from uuid import UUID

import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.core.errors
from dstack._internal.core.models.runs import Job, JobErrorCode, JobStatus, JobSubmission, Run
from dstack._internal.core.services.ssh import tunnel as ssh_tunnel
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel, RepoModel, RunModel
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    get_runner_ports,
    job_model_to_job_submission,
    terminate_job_submission_instance,
)
from dstack._internal.server.services.repos import get_code_model
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runs import (
    create_job_model_for_new_submission,
    run_model_to_run,
)
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


RUNNER_TIMEOUT_INTERVAL = timedelta(seconds=600)


async def process_running_jobs():
    async with get_session_ctx() as session:
        async with RUNNING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_([JobStatus.PROVISIONING, JobStatus.RUNNING]),
                    JobModel.id.not_in(RUNNING_PROCESSING_JOBS_IDS),
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
        res = await session.execute(select(JobModel).where(JobModel.id == job_id))
        job_model = res.scalar_one()
        res = await session.execute(
            select(RunModel)
            .where(RunModel.id == job_model.run_id)
            .options(joinedload(RunModel.project))
            .options(joinedload(RunModel.user))
            .options(joinedload(RunModel.repo))
        )
        run_model = res.scalar()
        repo_model = run_model.repo
        project = run_model.project
        run = run_model_to_run(run_model)
        job = run.jobs[job_model.job_num]
        job_submission = job_model_to_job_submission(job_model)
        server_ssh_private_key = project.ssh_private_key
        if job_model.status == JobStatus.PROVISIONING:
            logger.debug("Polling provisioning job %s", job_model.job_name)
            code = await _get_job_code(
                session=session,
                repo=repo_model,
                code_hash=run.run_spec.repo_code_hash,
            )
            await run_async(
                _process_provisioning_job,
                job_model,
                run,
                job,
                job_submission,
                code,
                server_ssh_private_key,
            )
        else:
            logger.debug("Polling running job %s", job_model.job_name)
            new_job_model = await run_async(
                _process_running_job,
                run_model,
                job_model,
                run,
                job,
                job_submission,
                server_ssh_private_key,
            )
            if new_job_model is not None:
                session.add(new_job_model)
            if job_model.error_code == JobErrorCode.INTERRUPTED_BY_NO_CAPACITY:
                # JobErrorCode.INTERRUPTED_BY_NO_CAPACITY means that we could not connect to runner.
                # The instance may still be running (e.g. network issue), so we force termination.
                await terminate_job_submission_instance(
                    project=project,
                    job_submission=job_submission,
                )
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()


def _process_provisioning_job(
    job_model: JobModel,
    run: Run,
    job: Job,
    job_submission: JobSubmission,
    code: bytes,
    server_ssh_private_key: str,
):
    ports = get_runner_ports()
    try:
        with ssh_tunnel.RunnerTunnel(
            hostname=job_submission.job_provisioning_data.hostname,
            ssh_port=job_submission.job_provisioning_data.ssh_port,
            user=job_submission.job_provisioning_data.username,
            ports=ports,
            id_rsa=server_ssh_private_key,
        ):
            runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
            alive = runner_client.healthcheck()
            if not alive:
                logger.debug("Runner for job %s is not available yet", job_model.job_name)
                if job_submission.age > RUNNER_TIMEOUT_INTERVAL:
                    logger.warning(
                        "Job %s failed because runner has not become available in time.",
                        job_model.job_name,
                    )
                    job_model.status = JobStatus.FAILED
                    job_model.error_code = JobErrorCode.WAITING_RUNNER_LIMIT_EXCEEDED
                return
            logger.debug("Submitting job %s...", job_model.job_name)
            runner_client.submit_job(
                run_spec=run.run_spec,
                job_spec=job.job_spec,
                secrets={},
                repo_credentials=None,
            )
            logger.debug("Uploading code %s...", job_model.job_name)
            runner_client.upload_code(code)
            logger.debug("Running job %s...", job_model.job_name)
            runner_client.run_job()
            job_model.status = JobStatus.RUNNING
            logger.debug("Job %s is running", job_model.job_name)
    except dstack._internal.core.errors.SSHError:
        logger.debug("Cannot establish ssh connection to job %s instance", job_model.job_name)


_SSH_MAX_RETRY = 3
_SSH_RETRY_INTERVAl = 1


def _process_running_job(
    run_model: RunModel,
    job_model: JobModel,
    run: Run,
    job: Job,
    job_submission: JobSubmission,
    server_ssh_private_key: str,
) -> Optional[JobModel]:
    """Polls the runner for job updates and updates `job_model`.

    :return: JobModel for new submission if re-submission is required (e.g. interrupted spot).
    """
    ports = get_runner_ports()
    for _ in range(_SSH_MAX_RETRY):
        try:
            with ssh_tunnel.RunnerTunnel(
                hostname=job_submission.job_provisioning_data.hostname,
                ssh_port=job_submission.job_provisioning_data.ssh_port,
                user=job_submission.job_provisioning_data.username,
                ports=ports,
                id_rsa=server_ssh_private_key,
            ):
                runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
                timestamp = 0
                if job_model.runner_timestamp is not None:
                    timestamp = job_model.runner_timestamp
                resp = runner_client.pull(timestamp)
                job_model.runner_timestamp = resp.last_updated
                logs_services.write_logs(
                    project=run_model.project,
                    run_name=run_model.run_name,
                    job_submission_id=job_model.id,
                    runner_logs=resp.runner_logs,
                    job_logs=resp.job_logs,
                )
                if len(resp.job_states) == 0:
                    logger.debug("Job %s status not changed", job_model.job_name)
                    return
                last_job_state = resp.job_states[-1]
                job_model.status = last_job_state.state
                logger.debug("Updated job %s status to %s", job_model.job_name, job_model.status)
                break
        except dstack._internal.core.errors.SSHError:
            logger.debug("Cannot establish ssh connection to job %s instance", job_model.job_name)
        except (requests.ConnectionError, requests.Timeout):
            logger.debug("Failed to connect to job %s runner", job_model.job_name)
        time.sleep(_SSH_RETRY_INTERVAl)
    else:
        job_model.status = JobStatus.FAILED
        job_model.error_code = JobErrorCode.INTERRUPTED_BY_NO_CAPACITY
        if job.is_retry_active():
            if job_submission.job_provisioning_data.instance_type.resources.spot:
                new_job_model = create_job_model_for_new_submission(
                    run_model=run_model,
                    job=job,
                    status=JobStatus.PENDING,
                )
                return new_job_model
    return None


async def _get_job_code(session: AsyncSession, repo: RepoModel, code_hash: str) -> bytes:
    code_model = await get_code_model(session=session, repo=repo, code_hash=code_hash)
    if code_model is not None:
        return code_model.blob
    return b""
