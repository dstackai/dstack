import asyncio
from datetime import timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.backends.base.backend import Backend
from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    RunTerminationReason,
)
from dstack._internal.server import settings
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events, services
from dstack._internal.server.services.instances import (
    format_instance_blocks_for_event,
    get_instance_ssh_private_keys,
    switch_instance_status,
)
from dstack._internal.server.services.jobs import (
    get_job_provisioning_data,
    get_job_runtime_data,
    switch_job_status,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.volumes import (
    list_project_volume_models,
    volume_model_to_volume,
)
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common
from dstack._internal.utils.common import (
    get_current_datetime,
    get_or_error,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


# NOTE: This scheduled task is going to be deprecated in favor of `JobTerminatingPipeline`.
# If this logic changes before removal, keep `pipeline_tasks/jobs_terminating.py` in sync.
async def process_terminating_jobs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_terminating_job())
    await asyncio.gather(*tasks)


@sentry_utils.instrument_scheduled_task
async def _process_next_terminating_job():
    job_lock, job_lockset = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
    instance_lock, instance_lockset = get_locker(get_db().dialect_name).get_lockset(
        InstanceModel.__tablename__
    )
    async with get_session_ctx() as session:
        async with job_lock, instance_lock:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.id.not_in(job_lockset),
                    JobModel.status == JobStatus.TERMINATING,
                    or_(
                        JobModel.remove_at.is_(None),
                        JobModel.remove_at < get_current_datetime(),
                    ),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True, key_share=True)
            )
            job_model = res.scalar()
            if job_model is None:
                return
            if job_model.used_instance_id is not None:
                res = await session.execute(
                    select(InstanceModel)
                    .where(
                        InstanceModel.id == job_model.used_instance_id,
                        InstanceModel.id.not_in(instance_lockset),
                        InstanceModel.lock_expires_at.is_(None),
                    )
                    .with_for_update(skip_locked=True, key_share=True)
                )
                instance_model = res.scalar()
                if instance_model is None:
                    # InstanceModel is locked
                    return
                instance_lockset.add(instance_model.id)
            job_lockset.add(job_model.id)
        job_model_id = job_model.id
        instance_model_id = job_model.used_instance_id
        try:
            await _process_job(
                session=session,
                job_model=job_model,
            )
        finally:
            job_lockset.difference_update([job_model_id])
            instance_lockset.difference_update([instance_model_id])


async def _process_job(session: AsyncSession, job_model: JobModel):
    logger.debug("%s: terminating job", fmt(job_model))
    res = await session.execute(
        select(InstanceModel)
        .where(InstanceModel.id == job_model.used_instance_id)
        .options(
            joinedload(InstanceModel.project).joinedload(ProjectModel.backends),
            joinedload(InstanceModel.volume_attachments).joinedload(VolumeAttachmentModel.volume),
            joinedload(InstanceModel.jobs).load_only(JobModel.id),
        )
    )
    instance_model = res.unique().scalar()
    if job_model.volumes_detached_at is None:
        await _process_terminating_job(session, job_model, instance_model)
    else:
        instance_model = get_or_error(instance_model)
        await _process_volumes_detaching(session, job_model, instance_model)
    job_model.last_processed_at = get_current_datetime()
    await session.commit()


async def _process_terminating_job(
    session: AsyncSession,
    job_model: JobModel,
    instance_model: Optional[InstanceModel],
):
    """
    Stops the job: tells shim to stop the container, detaches the job from the instance,
    and detaches volumes from the instance.
    Graceful stop should already be done by `process_terminating_run`.
    Caller must acquire the locks on the job and the job's instance.
    """
    if instance_model is None:
        # Possible if the job hasn't been assigned an instance yet
        await services.unregister_replica(session, job_model)
        _set_job_termination_status(session, job_model)
        return

    all_volumes_detached: bool = True
    jrd = get_job_runtime_data(job_model)
    jpd = get_job_provisioning_data(job_model)
    volume_models = await _get_job_volume_models(
        session=session,
        job_model=job_model,
        instance_model=instance_model,
        jrd=jrd,
    )
    if jpd is not None:
        logger.debug("%s: stopping container", fmt(job_model))
        ssh_private_keys = get_instance_ssh_private_keys(instance_model)
        if not await _stop_container(job_model, jpd, ssh_private_keys):
            # The dangling container can be removed later during instance processing
            logger.warning(
                (
                    "%s: could not stop container, possibly due to a communication error."
                    " See debug logs for details."
                    " Ignoring, can attempt to remove the container later"
                ),
                fmt(job_model),
            )
        if len(volume_models) > 0:
            logger.info("Detaching volumes: %s", [v.name for v in volume_models])
            all_volumes_detached = await _detach_volumes_from_job_instance(
                session=session,
                project=instance_model.project,
                job_model=job_model,
                jpd=jpd,
                instance_model=instance_model,
                volume_models=volume_models,
            )

    instance_model.busy_blocks -= _get_job_occupied_blocks(jrd)
    if instance_model.status != InstanceStatus.BUSY or jpd is None or not jpd.dockerized:
        # Terminate instances that:
        # - have not finished provisioning yet
        # - belong to container-based backends, and hence cannot be reused
        if instance_model.status not in InstanceStatus.finished_statuses():
            instance_model.termination_reason = InstanceTerminationReason.JOB_FINISHED
            switch_instance_status(session, instance_model, InstanceStatus.TERMINATING)
    elif not [j for j in instance_model.jobs if j.id != job_model.id]:
        # no other jobs besides this one
        switch_instance_status(session, instance_model, InstanceStatus.IDLE)

    # The instance should be released even if detach fails
    # so that stuck volumes don't prevent the instance from terminating.
    job_model.instance_id = None
    instance_model.last_job_processed_at = common.get_current_datetime()

    events.emit(
        session,
        (
            "Job unassigned from instance."
            f" Instance blocks: {format_instance_blocks_for_event(instance_model)}"
        ),
        actor=events.SystemActor(),
        targets=[
            events.Target.from_model(job_model),
            events.Target.from_model(instance_model),
        ],
    )

    # Volumes are not locked because no other place can update attached active volumes.
    for volume_model in volume_models:
        volume_model.last_job_processed_at = common.get_current_datetime()

    await services.unregister_replica(session, job_model)
    if all_volumes_detached:
        # Do not terminate while some volumes are not detached.
        _set_job_termination_status(session, job_model)


async def _get_job_volume_models(
    session: AsyncSession,
    job_model: JobModel,
    instance_model: InstanceModel,
    jrd: Optional[JobRuntimeData],
) -> list[VolumeModel]:
    volume_names = (
        jrd.volume_names
        if jrd and jrd.volume_names
        else [va.volume.name for va in instance_model.volume_attachments]
    )
    if len(volume_names) == 0:
        return []
    return await list_project_volume_models(
        session=session, project=instance_model.project, names=volume_names
    )


def _get_job_occupied_blocks(jrd: Optional[JobRuntimeData]) -> int:
    if jrd is not None and jrd.offer is not None:
        return jrd.offer.blocks
    # Old job submitted before jrd or blocks were introduced
    return 1


async def _process_volumes_detaching(
    session: AsyncSession,
    job_model: JobModel,
    instance_model: InstanceModel,
):
    """
    Called after job's volumes have been soft detached to check if they are detached.
    Terminates the job when all the volumes are detached.
    If the volumes fail to detach, force detaches them.
    """
    jpd = get_or_error(get_job_provisioning_data(job_model))
    jrd = get_job_runtime_data(job_model)
    volume_models = await _get_job_volume_models(
        session=session,
        job_model=job_model,
        instance_model=instance_model,
        jrd=jrd,
    )
    logger.info("Detaching volumes: %s", [v.name for v in volume_models])
    all_volumes_detached = await _detach_volumes_from_job_instance(
        session=session,
        project=instance_model.project,
        job_model=job_model,
        jpd=jpd,
        instance_model=instance_model,
        volume_models=volume_models,
    )
    if all_volumes_detached:
        # Do not terminate the job while some volumes are not detached.
        # If force detach never succeeds, the job will be stuck terminating.
        # The job releases the instance when soft detaching, so the instance won't be stuck.
        _set_job_termination_status(session, job_model)


def _set_job_termination_status(session: AsyncSession, job_model: JobModel):
    if job_model.termination_reason is not None:
        status = job_model.termination_reason.to_status()
    else:
        status = JobStatus.FAILED
    switch_job_status(session, job_model, status)


async def _stop_container(
    job_model: JobModel,
    job_provisioning_data: JobProvisioningData,
    ssh_private_keys: tuple[str, Optional[str]],
) -> bool:
    if job_provisioning_data.dockerized:
        # send a request to the shim to terminate the docker container
        # SSHError and RequestException are caught in the `runner_ssh_tunner` decorator
        return await common.run_async(
            _shim_submit_stop,
            ssh_private_keys,
            job_provisioning_data,
            None,
            job_model,
        )
    return True


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT])
def _shim_submit_stop(ports: dict[int, int], job_model: JobModel) -> bool:
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: can't stop container, shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    # we force-kill container because the runner had time to gracefully stop the job
    if shim_client.is_api_v2_supported():
        if job_model.termination_reason is None:
            reason = None
        else:
            reason = job_model.termination_reason.value
        shim_client.terminate_task(
            task_id=job_model.id,
            reason=reason,
            message=job_model.termination_reason_message,
            timeout=0,
        )
        # maybe somehow postpone removing old tasks to allow inspecting failed jobs without
        # the following setting?
        if not settings.SERVER_KEEP_SHIM_TASKS:
            shim_client.remove_task(task_id=job_model.id)
    else:
        shim_client.stop(force=True)
    return True


async def _detach_volumes_from_job_instance(
    session: AsyncSession,
    project: ProjectModel,
    job_model: JobModel,
    jpd: JobProvisioningData,
    instance_model: InstanceModel,
    volume_models: list[VolumeModel],
) -> bool:
    job_spec = JobSpec.__response__.parse_raw(job_model.job_spec_data)
    backend = await backends_services.get_project_backend_by_type(
        project=project,
        backend_type=jpd.backend,
    )
    if backend is None:
        logger.error(
            "Failed to detach volumes from %s. Backend not available.", instance_model.name
        )
        return False

    all_detached = True
    detached_volumes = []
    run_termination_reason = await _get_run_termination_reason(session, job_model)
    for volume_model in volume_models:
        detached = await _detach_volume_from_job_instance(
            backend=backend,
            job_model=job_model,
            jpd=jpd,
            job_spec=job_spec,
            instance_model=instance_model,
            volume_model=volume_model,
            run_termination_reason=run_termination_reason,
        )
        if detached:
            detached_volumes.append(volume_model)
        else:
            all_detached = False

    if job_model.volumes_detached_at is None:
        job_model.volumes_detached_at = common.get_current_datetime()
    detached_volumes_ids = {v.id for v in detached_volumes}
    instance_model.volume_attachments = [
        va for va in instance_model.volume_attachments if va.volume_id not in detached_volumes_ids
    ]
    return all_detached


async def _detach_volume_from_job_instance(
    backend: Backend,
    job_model: JobModel,
    jpd: JobProvisioningData,
    job_spec: JobSpec,
    instance_model: InstanceModel,
    volume_model: VolumeModel,
    run_termination_reason: Optional[RunTerminationReason],
) -> bool:
    detached = True
    volume = volume_model_to_volume(volume_model)
    if volume.provisioning_data is None or not volume.provisioning_data.detachable:
        # Backends without `detach_volume` detach volumes automatically
        return detached
    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    try:
        if job_model.volumes_detached_at is None:
            # We haven't tried detaching volumes yet, try soft detach first
            await common.run_async(
                compute.detach_volume,
                volume=volume,
                provisioning_data=jpd,
                force=False,
            )
            # For some backends, the volume may be detached immediately
            detached = await common.run_async(
                compute.is_volume_detached,
                volume=volume,
                provisioning_data=jpd,
            )
        else:
            detached = await common.run_async(
                compute.is_volume_detached,
                volume=volume,
                provisioning_data=jpd,
            )
            if not detached and _should_force_detach_volume(
                job_model,
                run_termination_reason=run_termination_reason,
                stop_duration=job_spec.stop_duration,
            ):
                logger.info(
                    "Force detaching volume %s from %s",
                    volume_model.name,
                    instance_model.name,
                )
                await common.run_async(
                    compute.detach_volume,
                    volume=volume,
                    provisioning_data=jpd,
                    force=True,
                )
                # Let the next iteration check if force detach worked
    except BackendError as e:
        logger.error(
            "Failed to detach volume %s from %s: %s",
            volume_model.name,
            instance_model.name,
            repr(e),
        )
    except Exception:
        logger.exception(
            "Got exception when detaching volume %s from instance %s",
            volume_model.name,
            instance_model.name,
        )
    return detached


async def _get_run_termination_reason(
    session: AsyncSession, job_model: JobModel
) -> Optional[RunTerminationReason]:
    res = await session.execute(
        select(RunModel.termination_reason).where(RunModel.id == job_model.run_id)
    )
    return res.scalar_one_or_none()


_MIN_FORCE_DETACH_WAIT_PERIOD = timedelta(seconds=60)


def _should_force_detach_volume(
    job_model: JobModel,
    run_termination_reason: Optional[RunTerminationReason],
    stop_duration: Optional[int],
) -> bool:
    return (
        job_model.volumes_detached_at is not None
        and common.get_current_datetime()
        > job_model.volumes_detached_at + _MIN_FORCE_DETACH_WAIT_PERIOD
        and (
            job_model.termination_reason == JobTerminationReason.ABORTED_BY_USER
            or run_termination_reason == RunTerminationReason.ABORTED_BY_USER
            or stop_duration is not None
            and common.get_current_datetime()
            > job_model.volumes_detached_at + timedelta(seconds=stop_duration)
        )
    )
