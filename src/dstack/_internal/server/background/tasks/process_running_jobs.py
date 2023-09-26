import asyncio
from typing import Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import Job, JobStatus, JobSubmission, Run
from dstack._internal.core.services.ssh import tunnel as ssh_tunnel
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import CodeModel, JobModel, RepoModel, RunModel
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    get_runner_ports,
    job_model_to_job_submission,
)
from dstack._internal.server.services.repos import get_code_model
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_running_jobs():
    async with get_session_ctx() as session:
        async with RUNNING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_([JobStatus.PROVISIONING, JobStatus.RUNNING]),
                    JobModel.id.not_in(RUNNING_PROCESSING_JOBS_IDS),
                )
                .order_by(JobModel.last_processed_at.desc())
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
            select(JobModel)
            .where(JobModel.id == job_id)
            .options(joinedload(JobModel.run).joinedload(RunModel.project))
            .options(joinedload(JobModel.run).joinedload(RunModel.user))
            .options(joinedload(JobModel.run).joinedload(RunModel.repo))
        )
        job_model = res.scalar_one()
        run_model = job_model.run
        repo_model = run_model.repo
        project = run_model.project
        run = run_model_to_run(run_model, include_job_submissions=False)
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
            await run_async(
                _process_running_job,
                job_model,
                run,
                job,
                job_submission,
                server_ssh_private_key,
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
        with ssh_tunnel.SSHTunnel(
            hostname=job_submission.job_provisioning_data.hostname,
            ssh_port=job_submission.job_provisioning_data.ssh_port,
            user=job_submission.job_provisioning_data.username,
            ports=ports,
            id_rsa=server_ssh_private_key.encode(),
        ):
            runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
            alive = runner_client.healthcheck()
            if not alive:
                logger.debug("Runner %s is not alive", job_model.job_name)
                # TODO if runner never becomes alive?
                # Fail after a deadline?
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
    except (ssh_tunnel.SSHConnectionRefusedError, ssh_tunnel.SSHTimeoutError):
        pass


def _process_running_job(
    job_model: JobModel,
    run: Run,
    job: Job,
    job_submission: JobSubmission,
    server_ssh_private_key: str,
):
    ports = get_runner_ports()
    with ssh_tunnel.SSHTunnel(
        hostname=job_submission.job_provisioning_data.hostname,
        ssh_port=job_submission.job_provisioning_data.ssh_port,
        user=job_submission.job_provisioning_data.username,
        ports=ports,
        id_rsa=server_ssh_private_key.encode(),
    ):
        runner_client = client.RunnerClient(port=ports[client.REMOTE_RUNNER_PORT])
        timestamp = 0
        if job_model.runner_timestamp is not None:
            timestamp = job_model.runner_timestamp
        resp = runner_client.pull(timestamp)
        job_model.runner_timestamp = resp.last_updated
        if len(resp.job_states) == 0:
            logger.debug("Got 0 job %s states", job_model.job_name)
            return
        last_job_state = resp.job_states[-1]
        job_model.status = last_job_state.state
        logger.debug("Updated job %s status to %s", job_model.job_name, job_model.status)
        # TODO Write logs
        # TODO If retry is active, update job status to PENDING.


async def _get_job_code(session: AsyncSession, repo: RepoModel, code_hash: str) -> bytes:
    code_model = await get_code_model(session=session, repo=repo, code_hash=code_hash)
    if code_model is not None:
        return code_model.blob_hash
    return b""
