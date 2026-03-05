import logging
from datetime import timedelta
from typing import Optional

import gpuhunt
import requests
from sqlalchemy import func, select

from dstack._internal.core.backends.base.compute import (
    get_dstack_runner_download_url,
    get_dstack_runner_version,
    get_dstack_shim_download_url,
    get_dstack_shim_version,
)
from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server import settings as server_settings
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    TERMINATION_DEADLINE_OFFSET,
    HealthCheckCreate,
    ProcessResult,
    can_terminate_fleet_instances_on_idle_duration,
    get_instance_idle_duration,
    get_provisioning_deadline,
    set_health_update,
    set_status_update,
    set_unreachable_update,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceHealthCheckModel, InstanceModel
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import (
    ComponentInfo,
    ComponentStatus,
    InstanceHealthResponse,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services.instances import (
    get_instance_provisioning_data,
    get_instance_ssh_private_keys,
    is_ssh_instance,
    remove_dangling_tasks_from_instance,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def process_idle_timeout(instance_model: InstanceModel) -> Optional[ProcessResult]:
    if not (
        instance_model.status == InstanceStatus.IDLE
        and instance_model.termination_policy == TerminationPolicy.DESTROY_AFTER_IDLE
        and not instance_model.jobs
    ):
        return None
    # Do not terminate instances on idle duration if fleet is already at `nodes.min`.
    # This is an optimization to avoid terminate-create loop.
    # There may be race conditions since we don't take the fleet lock.
    # That's ok: in the worst case we go below `nodes.min`, but
    # the fleet consolidation logic will provision new nodes.
    if instance_model.fleet is not None and not can_terminate_fleet_instances_on_idle_duration(
        instance_model.fleet
    ):
        return None

    idle_duration = get_instance_idle_duration(instance_model)
    if idle_duration <= timedelta(seconds=instance_model.termination_idle_time):
        return None

    result = ProcessResult()
    set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.TERMINATING,
        termination_reason=InstanceTerminationReason.IDLE_TIMEOUT,
        termination_reason_message=f"Instance idle for {idle_duration.seconds}s",
    )
    return result


async def check_instance(instance_model: InstanceModel) -> ProcessResult:
    result = ProcessResult()
    if (
        instance_model.status == InstanceStatus.BUSY
        and instance_model.jobs
        and all(job.status.is_finished() for job in instance_model.jobs)
    ):
        # A busy instance could have no active jobs due to this bug:
        # https://github.com/dstackai/dstack/issues/2068
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.JOB_FINISHED,
        )
        logger.warning(
            "Detected busy instance %s with finished job. Marked as TERMINATING",
            instance_model.name,
            extra={
                "instance_name": instance_model.name,
                "instance_status": instance_model.status.value,
            },
        )
        return result

    job_provisioning_data = get_or_error(get_instance_provisioning_data(instance_model))
    if job_provisioning_data.hostname is None:
        return await _process_wait_for_instance_provisioning_data(
            instance_model=instance_model,
            job_provisioning_data=job_provisioning_data,
        )

    if not job_provisioning_data.dockerized:
        if instance_model.status == InstanceStatus.PROVISIONING:
            set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.BUSY,
            )
        return result

    check_instance_health = await _should_check_instance_health(instance_model.id)
    instance_check = await _run_instance_check(
        instance_model=instance_model,
        job_provisioning_data=job_provisioning_data,
        check_instance_health=check_instance_health,
    )
    health_status = _get_health_status_for_instance_check(
        instance_model=instance_model,
        instance_check=instance_check,
        check_instance_health=check_instance_health,
    )
    _log_instance_check_result(
        instance_model=instance_model,
        instance_check=instance_check,
        health_status=health_status,
        check_instance_health=check_instance_health,
    )

    if instance_check.has_health_checks():
        # ensured by has_health_checks()
        assert instance_check.health_response is not None
        result.health_check_create = HealthCheckCreate(
            instance_id=instance_model.id,
            collected_at=get_current_datetime(),
            status=health_status,
            response=instance_check.health_response.json(),
        )

    set_health_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        health=health_status,
    )
    set_unreachable_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        unreachable=not instance_check.reachable,
    )

    if instance_check.reachable:
        result.instance_update_map["termination_deadline"] = None
        if instance_model.status == InstanceStatus.PROVISIONING:
            set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.IDLE if not instance_model.jobs else InstanceStatus.BUSY,
            )
        return result

    now = get_current_datetime()
    if not is_ssh_instance(instance_model) and instance_model.termination_deadline is None:
        result.instance_update_map["termination_deadline"] = now + TERMINATION_DEADLINE_OFFSET

    if (
        instance_model.status == InstanceStatus.PROVISIONING
        and instance_model.started_at is not None
    ):
        provisioning_deadline = get_provisioning_deadline(
            instance_model=instance_model,
            job_provisioning_data=job_provisioning_data,
        )
        if now > provisioning_deadline:
            set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.TERMINATING,
                termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
                termination_reason_message="Instance did not become reachable in time",
            )
    elif instance_model.status.is_available():
        deadline = instance_model.termination_deadline
        if deadline is not None and now > deadline:
            set_status_update(
                update_map=result.instance_update_map,
                instance_model=instance_model,
                new_status=InstanceStatus.TERMINATING,
                termination_reason=InstanceTerminationReason.UNREACHABLE,
            )
    return result


async def _should_check_instance_health(instance_id) -> bool:
    health_check_cutoff = get_current_datetime() - timedelta(
        seconds=server_settings.SERVER_INSTANCE_HEALTH_MIN_COLLECT_INTERVAL_SECONDS
    )
    async with get_session_ctx() as session:
        res = await session.execute(
            select(func.count(1)).where(
                InstanceHealthCheckModel.instance_id == instance_id,
                InstanceHealthCheckModel.collected_at > health_check_cutoff,
            )
        )
    return res.scalar_one() == 0


async def _run_instance_check(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
    check_instance_health: bool,
) -> InstanceCheck:
    ssh_private_keys = get_instance_ssh_private_keys(instance_model)
    instance_check = await run_async(
        _check_instance_inner,
        ssh_private_keys,
        job_provisioning_data,
        None,
        instance=instance_model,
        check_instance_health=check_instance_health,
    )
    # May return False if fails to establish ssh connection.
    if instance_check is False:
        return InstanceCheck(reachable=False, message="SSH or tunnel error")
    return instance_check


def _get_health_status_for_instance_check(
    instance_model: InstanceModel,
    instance_check: InstanceCheck,
    check_instance_health: bool,
) -> HealthStatus:
    if instance_check.reachable and check_instance_health:
        return instance_check.get_health_status()
    # Keep previous health status.
    return instance_model.health


def _log_instance_check_result(
    instance_model: InstanceModel,
    instance_check: InstanceCheck,
    health_status: HealthStatus,
    check_instance_health: bool,
) -> None:
    loglevel = logging.DEBUG
    if not instance_check.reachable and instance_model.status.is_available():
        loglevel = logging.WARNING
    elif check_instance_health and not health_status.is_healthy():
        loglevel = logging.WARNING
    logger.log(
        loglevel,
        "Instance %s check: reachable=%s health_status=%s message=%r",
        instance_model.name,
        instance_check.reachable,
        health_status.name,
        instance_check.message,
        extra={"instance_name": instance_model.name, "health_status": health_status},
    )


async def _process_wait_for_instance_provisioning_data(
    instance_model: InstanceModel,
    job_provisioning_data: JobProvisioningData,
) -> ProcessResult:
    result = ProcessResult()
    logger.debug("Waiting for instance %s to become running", instance_model.name)
    provisioning_deadline = get_provisioning_deadline(
        instance_model=instance_model,
        job_provisioning_data=job_provisioning_data,
    )
    if get_current_datetime() > provisioning_deadline:
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
            termination_reason_message="Backend did not complete provisioning in time",
        )
        return result

    backend = await backends_services.get_project_backend_by_type(
        project=instance_model.project,
        backend_type=job_provisioning_data.backend,
    )
    if backend is None:
        logger.warning(
            "Instance %s failed because instance's backend is not available",
            instance_model.name,
        )
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Backend not available",
        )
        return result

    try:
        await run_async(
            backend.compute().update_provisioning_data,
            job_provisioning_data,
            instance_model.project.ssh_public_key,
            instance_model.project.ssh_private_key,
        )
        result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
    except ProvisioningError as exc:
        logger.warning(
            "Error while waiting for instance %s to become running: %s",
            instance_model.name,
            repr(exc),
        )
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATING,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Error while waiting for instance to become running",
        )
    except Exception:
        logger.exception(
            "Got exception when updating instance %s provisioning data",
            instance_model.name,
        )
    return result


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _check_instance_inner(
    ports: dict[int, int],
    *,
    instance: InstanceModel,
    check_instance_health: bool = False,
) -> InstanceCheck:
    instance_health_response: Optional[InstanceHealthResponse] = None
    shim_client = runner_client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    method = shim_client.healthcheck
    try:
        healthcheck_response = method(unmask_exceptions=True)
        if check_instance_health:
            method = shim_client.get_instance_health
            instance_health_response = method()
    except requests.RequestException as exc:
        template = "shim.%s(): request error: %s"
        args = (method.__func__.__name__, exc)
        logger.debug(template, *args)
        return InstanceCheck(reachable=False, message=template % args)
    except Exception as exc:
        template = "shim.%s(): unexpected exception %s: %s"
        args = (method.__func__.__name__, exc.__class__.__name__, exc)
        logger.exception(template, *args)
        return InstanceCheck(reachable=False, message=template % args)

    try:
        remove_dangling_tasks_from_instance(shim_client, instance)
    except Exception as exc:
        logger.exception("%s: error removing dangling tasks: %s", fmt(instance), exc)

    # There should be no shim API calls after this function call since it can request shim restart.
    _maybe_install_components(instance, shim_client)
    return runner_client.healthcheck_response_to_instance_check(
        healthcheck_response,
        instance_health_response,
    )


def _maybe_install_components(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
) -> None:
    try:
        components = shim_client.get_components()
    except requests.RequestException as exc:
        logger.warning(
            "Instance %s: shim.get_components(): request error: %s", instance_model.name, exc
        )
        return
    if components is None:
        logger.debug("Instance %s: no components info", instance_model.name)
        return

    installed_shim_version: Optional[str] = None
    installation_requested = False

    if (runner_info := components.runner) is not None:
        installation_requested |= _maybe_install_runner(instance_model, shim_client, runner_info)
    else:
        logger.debug("Instance %s: no runner info", instance_model.name)

    if (shim_info := components.shim) is not None:
        if shim_info.status == ComponentStatus.INSTALLED:
            installed_shim_version = shim_info.version
        installation_requested |= _maybe_install_shim(instance_model, shim_client, shim_info)
    else:
        logger.debug("Instance %s: no shim info", instance_model.name)

    # old shim without `dstack-shim` component and `/api/shutdown` support
    # or the same version is already running
    # or we just requested installation of at least one component
    # or at least one component is already being installed
    # or at least one shim task won't survive restart
    running_shim_version = shim_client.get_version_string()
    if (
        installed_shim_version is None
        or installed_shim_version == running_shim_version
        or installation_requested
        or any(component.status == ComponentStatus.INSTALLING for component in components)
        or not shim_client.is_safe_to_restart()
    ):
        return

    if shim_client.shutdown(force=False):
        logger.debug(
            "Instance %s: restarting shim %s -> %s",
            instance_model.name,
            running_shim_version,
            installed_shim_version,
        )
    else:
        logger.debug("Instance %s: cannot restart shim", instance_model.name)


def _maybe_install_runner(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
    runner_info: ComponentInfo,
) -> bool:
    # For developers:
    # * To install the latest dev build for the current branch from the CI,
    #   set DSTACK_USE_LATEST_FROM_BRANCH=1.
    # * To provide your own build, set DSTACK_RUNNER_VERSION_URL and DSTACK_RUNNER_DOWNLOAD_URL.
    expected_version = get_dstack_runner_version()
    if expected_version is None:
        logger.debug("Cannot determine the expected runner version")
        return False

    installed_version = runner_info.version
    logger.debug(
        "Instance %s: runner status=%s installed_version=%s",
        instance_model.name,
        runner_info.status.value,
        installed_version or "(no version)",
    )
    if runner_info.status == ComponentStatus.INSTALLING:
        logger.debug("Instance %s: runner is already being installed", instance_model.name)
        return False
    if installed_version and installed_version == expected_version:
        logger.debug("Instance %s: expected runner version already installed", instance_model.name)
        return False

    url = get_dstack_runner_download_url(
        arch=_get_instance_cpu_arch(instance_model),
        version=expected_version,
    )
    logger.debug(
        "Instance %s: installing runner %s -> %s from %s",
        instance_model.name,
        installed_version or "(no version)",
        expected_version,
        url,
    )
    try:
        shim_client.install_runner(url)
        return True
    except requests.RequestException as exc:
        logger.warning("Instance %s: shim.install_runner(): %s", instance_model.name, exc)
    return False


def _maybe_install_shim(
    instance_model: InstanceModel,
    shim_client: runner_client.ShimClient,
    shim_info: ComponentInfo,
) -> bool:
    # For developers:
    # * To install the latest dev build for the current branch from the CI,
    #   set DSTACK_USE_LATEST_FROM_BRANCH=1.
    # * To provide your own build, set DSTACK_SHIM_VERSION_URL and DSTACK_SHIM_DOWNLOAD_URL.
    expected_version = get_dstack_shim_version()
    if expected_version is None:
        logger.debug("Cannot determine the expected shim version")
        return False

    installed_version = shim_info.version
    logger.debug(
        "Instance %s: shim status=%s installed_version=%s running_version=%s",
        instance_model.name,
        shim_info.status.value,
        installed_version or "(no version)",
        shim_client.get_version_string(),
    )
    if shim_info.status == ComponentStatus.INSTALLING:
        logger.debug("Instance %s: shim is already being installed", instance_model.name)
        return False
    if installed_version and installed_version == expected_version:
        logger.debug("Instance %s: expected shim version already installed", instance_model.name)
        return False

    url = get_dstack_shim_download_url(
        arch=_get_instance_cpu_arch(instance_model),
        version=expected_version,
    )
    logger.debug(
        "Instance %s: installing shim %s -> %s from %s",
        instance_model.name,
        installed_version or "(no version)",
        expected_version,
        url,
    )
    try:
        shim_client.install_shim(url)
        return True
    except requests.RequestException as exc:
        logger.warning("Instance %s: shim.install_shim(): %s", instance_model.name, exc)
    return False


def _get_instance_cpu_arch(instance_model: InstanceModel) -> Optional[gpuhunt.CPUArchitecture]:
    job_provisioning_data = get_instance_provisioning_data(instance_model)
    if job_provisioning_data is None:
        return None
    return job_provisioning_data.instance_type.resources.cpu_arch
