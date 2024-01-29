from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import JobSpec, JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import GatewayModel, JobModel
from dstack._internal.server.services.gateways import gateway_connections_pool
from dstack._internal.server.services.jobs import (
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    job_model_to_job_submission,
    terminate_job_submission_instance,
)
from dstack._internal.server.services.logging import job_log
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_finished_jobs():
    async with get_session_ctx() as session:
        async with TERMINATING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.id.not_in(TERMINATING_PROCESSING_JOBS_IDS),
                    JobModel.removed.is_(False),
                    JobModel.status.in_(JobStatus.finished_statuses()),
                    or_(JobModel.remove_at.is_(None), JobModel.remove_at < get_current_datetime()),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)  # TODO(egor-s) process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return
            TERMINATING_PROCESSING_JOBS_IDS.add(job_model.id)
    try:
        await _process_job(job_id=job_model.id)
    finally:
        TERMINATING_PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel).where(JobModel.id == job_id).options(joinedload(JobModel.project))
        )
        job_model = res.scalar_one()
        job_submission = job_model_to_job_submission(job_model)
        job_spec = JobSpec.parse_raw(job_model.job_spec_data)
        if job_spec.gateway is not None:
            res = await session.execute(
                select(GatewayModel)
                .where(
                    GatewayModel.name == job_spec.gateway.gateway_name,
                    GatewayModel.project_id == job_model.project_id,
                )
                .options(joinedload(GatewayModel.gateway_compute))
            )
            gateway = res.scalar()
            if gateway is not None:
                if (
                    conn := await gateway_connections_pool.get(gateway.gateway_compute.ip_address)
                ) is None:
                    logger.warning(
                        "Gateway is not connected: %s", gateway.gateway_compute.ip_address
                    )
                try:
                    await run_async(
                        conn.client.unregister_service,
                        job_model.project.name,
                        job_spec.gateway.hostname,
                    )
                    logger.debug(*job_log("service is unregistered", job_model))
                except Exception as e:
                    logger.warning("failed to unregister service: %s", e)
        try:
            if job_submission.job_provisioning_data is not None:
                await terminate_job_submission_instance(
                    project=job_model.project,
                    job_submission=job_submission,
                )
            job_model.removed = True
            logger.info(*job_log("marked as removed", job_model))
        except Exception as e:
            job_model.removed = False
            logger.error(*job_log("failed to terminate job instance: %s", job_model, e))
        job_model.last_processed_at = get_current_datetime()
        await session.commit()
