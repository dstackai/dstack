from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import BackendError, NotYetTerminated
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    ProcessResult,
    get_termination_deadline,
    next_termination_retry_at,
    set_status_update,
)
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.instances import (
    get_instance_provisioning_data,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
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
        backend = await backends_services.get_project_backend_by_type(
            project=instance_model.project,
            backend_type=job_provisioning_data.backend,
        )
        if backend is None:
            logger.error(
                "Failed to terminate instance %s. Backend %s not available.",
                instance_model.name,
                job_provisioning_data.backend,
            )
        else:
            await _capture_final_data_transfer_bytes(instance_model, job_provisioning_data, result)
            logger.debug("Terminating runner instance %s", job_provisioning_data.hostname)
            try:
                await run_async(
                    backend.compute().terminate_instance,
                    job_provisioning_data.instance_id,
                    job_provisioning_data.region,
                    job_provisioning_data.backend_data,
                )
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
                logger.error(
                    "Failed all attempts to terminate instance %s."
                    " Please terminate the instance manually to avoid unexpected charges."
                    " Error: %r",
                    instance_model.name,
                    exc,
                    exc_info=not isinstance(exc, BackendError),
                )

    result.instance_update_map["deleted"] = True
    result.instance_update_map["deleted_at"] = NOW_PLACEHOLDER
    result.instance_update_map["finished_at"] = NOW_PLACEHOLDER
    set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATED,
    )
    return result


async def _capture_final_data_transfer_bytes(
    instance_model: InstanceModel,
    jpd: JobProvisioningData,
    result: ProcessResult,
) -> None:
    """Best-effort final read of data_transfer_bytes before the instance is destroyed."""
    try:
        health_response = await run_async(
            _read_instance_health,
            get_instance_ssh_private_keys(instance_model),
            jpd,
            instance=instance_model,
        )
        if health_response is not None and health_response.data_transfer_bytes is not None:
            result.instance_update_map["data_transfer_bytes"] = health_response.data_transfer_bytes
    except Exception as exc:
        logger.debug(
            "Failed to capture final data_transfer_bytes for %s: %s",
            instance_model.name,
            exc,
        )


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _read_instance_health(ports, *, instance):
    shim_client = runner_client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    return shim_client.get_instance_health()
