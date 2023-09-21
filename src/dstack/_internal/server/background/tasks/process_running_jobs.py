import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx, session_decorator
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import job_model_to_job_submission
from dstack._internal.server.services.runner import client, ssh
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.utils import common as common_utils

_PROCESSING_JOBS_LOCK = asyncio.Lock()
_PROCESSING_JOBS_IDS = set()


_LOCAL_RUNNER_PORT = 8383
_REMOTE_RUNNER_PORT = 10999


async def process_running_jobs():
    async with get_session_ctx() as session:
        async with _PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_([JobStatus.PROVISIONING, JobStatus.RUNNING]),
                    JobModel.id.not_in(_PROCESSING_JOBS_IDS),
                )
                .order_by(JobModel.last_processed_at.desc())
                .limit(1)  # TODO process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return

            _PROCESSING_JOBS_IDS.add(job_model.id)

    try:
        await _process_job(job_id=job_model.id)
    finally:
        async with _PROCESSING_JOBS_LOCK:
            _PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id: UUID):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel)
            .where(JobModel.id == job_id)
            .options(joinedload(JobModel.run).joinedload(RunModel.project))
            .options(joinedload(JobModel.run).joinedload(RunModel.user))
        )
        job_model = res.scalar_one()
        if job_model.status == JobStatus.PROVISIONING:
            await _process_provisioning_job(job_model=job_model)
        else:
            await _process_running_job(job_model=job_model)
        job_model.last_processed_at = common_utils.get_current_datetime()
        await session.commit()


async def _process_provisioning_job(job_model: JobModel):
    run_model = job_model.run
    project = run_model.project
    run = run_model_to_run(run_model, include_job_submissions=False)
    job = run.jobs[job_model.job_num]
    job_submission = job_model_to_job_submission(job_model)
    server_ssh_private_key = project.ssh_private_key
    try:
        with ssh.SSHTunnel(
            hostname=job_submission.job_provisioning_data.hostname,
            ports={_REMOTE_RUNNER_PORT: _LOCAL_RUNNER_PORT},
            id_rsa=server_ssh_private_key.encode(),
        ):
            runner_client = client.AsyncRunnerClient(port=_LOCAL_RUNNER_PORT)
            alive = await runner_client.healthcheck()
            if not alive:
                # TODO if runner never becomes alive?
                # Fail after a deadline?
                return
            await runner_client.submit_job(
                run_spec=run.run_spec,
                job_spec=job.job_spec,
                secrets={},
                repo_credentials=None,
            )
            await runner_client.upload_code("")
            await runner_client.run_job()
            job_model.status = JobStatus.RUNNING
    except (ssh.SSHConnectionRefusedError, ssh.SSHTimeoutError):
        pass


async def _process_running_job(job_model: JobModel):
    run_model = job_model.run
    project = run_model.project
    run = run_model_to_run(run_model, include_job_submissions=False)
    job = run.jobs[job_model.job_num]
    job_submission = job_model_to_job_submission(job_model)
    server_ssh_private_key = project.ssh_private_key
    with ssh.SSHTunnel(
        hostname=job_submission.job_provisioning_data.hostname,
        ports={_REMOTE_RUNNER_PORT: _LOCAL_RUNNER_PORT},
        id_rsa=server_ssh_private_key.encode(),
    ):
        runner_client = client.AsyncRunnerClient(port=_LOCAL_RUNNER_PORT)
        resp = await runner_client.pull(0)
        if len(resp.job_states) == 0:
            return
        last_job_state = resp.job_states[-1]
        job_model.status = last_job_state.state
        # TODO If retry is active, update job status to PENDING.
