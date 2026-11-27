from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.backends.features import get_backends_with_resource_listing_support
from dstack._internal.core.errors import (
    BackendError,
    NotYetTerminated,
    SSHError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import OrphanCleanupMode
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    ProcessResult,
    get_termination_deadline,
    next_termination_retry_at,
    set_status_update,
)
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.services.backends import cache as backends_cache
from dstack._internal.server.services.instances import (
    get_instance_provisioning_data,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.runner.pool import (
    instance_connection_pool,
)
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def terminate_instance(instance_model: InstanceModel) -> ProcessResult:
    result = ProcessResult()
    now = get_current_datetime()
    if (
        instance_model.last_termination_retry_at is not None
        and next_termination_retry_at(instance_model.last_termination_retry_at) > now
    ):
        return result

    job_provisioning_data = get_instance_provisioning_data(instance_model)
    if job_provisioning_data is not None and job_provisioning_data.backend != BackendType.REMOTE:
        try:
            await _terminate_in_backend(instance_model, job_provisioning_data)
            result.release_volume_attachments = list(job_provisioning_data.volume_mounts or ())
        except Exception as exc:
            first_retry_at = instance_model.first_termination_retry_at
            if first_retry_at is None:
                first_retry_at = now
                result.instance_update_map["first_termination_retry_at"] = NOW_PLACEHOLDER
            result.instance_update_map["last_termination_retry_at"] = NOW_PLACEHOLDER
            if next_termination_retry_at(now) < get_termination_deadline(first_retry_at):
                if isinstance(exc, NotYetTerminated):
                    logger.debug(
                        "Instance %s termination in progress: %s",
                        instance_model.name,
                        exc,
                    )
                else:
                    logger.warning(
                        "Failed to terminate instance %s. Will retry. Error: %r",
                        instance_model.name,
                        exc,
                        exc_info=not isinstance(exc, BackendError),
                    )
                return result
            if job_provisioning_data.volume_mounts:
                # Keep the VM and its attachment records until termination is confirmed.
                if not isinstance(exc, NotYetTerminated) and (
                    instance_model.last_termination_retry_at is None
                    or next_termination_retry_at(instance_model.last_termination_retry_at)
                    < get_termination_deadline(first_retry_at)
                ):
                    result.event_messages.append(
                        "Volume attachments retained until dstack confirms the VM is gone. "
                        "dstack will keep retrying. "
                        f"Last error: {_format_error(exc)}"
                    )
                logger.warning("Instance %s termination pending: %r", instance_model.name, exc)
                return result
            next_step = "Please terminate the instance manually to avoid unexpected charges."
            if _is_to_be_deleted_by_orphan_cleanup(instance_model, job_provisioning_data):
                next_step = "Orphan cleanup will retry deleting the instance."
            result.event_messages.append(
                f"Failed all attempts to terminate instance in the backend. {next_step}"
                f" Last error: {_format_error(exc)}"
            )
            logger.error(
                "Failed all attempts to terminate instance %s. %s Error: %r",
                instance_model.name,
                next_step,
                exc,
                exc_info=not isinstance(exc, BackendError),
            )

    if job_provisioning_data is not None:
        instance_connection_pool.drop_by_jpd(job_provisioning_data)

    result.instance_update_map["deleted"] = True
    result.instance_update_map["deleted_at"] = NOW_PLACEHOLDER
    result.instance_update_map["finished_at"] = NOW_PLACEHOLDER
    set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATED,
    )
    # The fleet may have become empty and ready to be deleted.
    result.wake_fleet_id = instance_model.fleet_id
    return result


async def _terminate_in_backend(
    instance_model: InstanceModel, job_provisioning_data: JobProvisioningData
):
    async with backends_cache.lease_project_backend_by_type(
        project=instance_model.project,
        backend_type=job_provisioning_data.backend,
    ) as backend:
        if backend is None:
            if job_provisioning_data.volume_mounts:
                raise BackendError("Backend unavailable while terminating a VM with volumes")
            logger.error(
                "Failed to terminate instance %s. Backend %s not available.",
                instance_model.name,
                job_provisioning_data.backend,
            )
            return
        compute = backend.compute()
        if job_provisioning_data.volume_mounts and job_provisioning_data.hostname:
            assert isinstance(compute, ComputeWithVolumeSupport)
            paths = await run_async(compute.get_volume_mounts_to_sync, job_provisioning_data)
            if paths is None:
                # Disappearance was confirmed without a guest. A second lookup could
                # observe a running VM and delete it without ever flushing its mounts.
                return
            if paths:
                await _sync_volume_mounts(instance_model, job_provisioning_data, paths)
        logger.debug("Terminating runner instance %s", job_provisioning_data.hostname)
        await run_async(
            compute.terminate_instance,
            job_provisioning_data.instance_id,
            job_provisioning_data.region,
            job_provisioning_data.backend_data,
        )


async def _sync_volume_mounts(
    instance_model: InstanceModel, job_provisioning_data: JobProvisioningData, paths: list[str]
) -> None:
    conn = await run_async(
        instance_connection_pool.get_or_open,
        get_instance_ssh_private_keys(instance_model),
        job_provisioning_data,
        None,
    )
    if conn is None:
        raise BackendError("Could not connect to the VM to flush its volumes")
    try:
        await conn.sync_volume_mounts(paths)
    except SSHError as e:
        raise BackendError("Could not flush the VM's volume mounts") from e


def _format_error(exc: Exception) -> str:
    if isinstance(exc, BackendError):
        return str(exc) or type(exc).__name__
    return type(exc).__name__  # avoid leaking internal details


def _is_to_be_deleted_by_orphan_cleanup(
    instance_model: InstanceModel, job_provisioning_data: JobProvisioningData
) -> bool:
    return (
        settings.ORPHAN_CLEANUP_MODE == OrphanCleanupMode.DELETE
        and instance_model.provider_ref is not None
        and job_provisioning_data.backend in get_backends_with_resource_listing_support()
    )
