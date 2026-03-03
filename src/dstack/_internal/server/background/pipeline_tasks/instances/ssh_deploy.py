import asyncio
from datetime import timedelta
from typing import Any, Optional

from paramiko.pkey import PKey
from paramiko.ssh_exception import PasswordRequiredException
from pydantic import ValidationError

from dstack._internal import settings
from dstack._internal.core.backends.base.compute import (
    GoArchType,
    get_dstack_runner_binary_path,
    get_dstack_shim_binary_path,
    get_dstack_working_dir,
    get_shim_env,
    get_shim_pre_start_commands,
)
from dstack._internal.core.errors import SSHProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceStatus,
    InstanceTerminationReason,
    RemoteConnectionInfo,
)
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.background.pipeline_tasks.base import NOW_PLACEHOLDER
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    PROVISIONING_TIMEOUT_SECONDS,
    ProcessResult,
    set_status_update,
    ssh_keys_to_pkeys,
)
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import HealthcheckResponse
from dstack._internal.server.services.instances import get_instance_remote_connection_info
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.offers import is_divisible_into_blocks
from dstack._internal.server.services.runner import client as runner_client
from dstack._internal.server.services.ssh_fleets.provisioning import (
    detect_cpu_arch,
    get_host_info,
    get_paramiko_connection,
    get_shim_healthcheck,
    host_info_to_instance_type,
    remove_dstack_runner_if_exists,
    remove_host_info_if_exists,
    run_pre_start_commands,
    run_shim_as_systemd_service,
    upload_envs,
)
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.network import get_ip_from_network, is_ip_among_addresses

logger = get_logger(__name__)


async def add_ssh_instance(instance_model: InstanceModel) -> ProcessResult:
    result = ProcessResult()
    logger.info("Adding ssh instance %s...", instance_model.name)

    retry_duration_deadline = instance_model.created_at + timedelta(
        seconds=PROVISIONING_TIMEOUT_SECONDS
    )
    if retry_duration_deadline < get_current_datetime():
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.PROVISIONING_TIMEOUT,
            termination_reason_message=(
                f"Failed to add SSH instance in {PROVISIONING_TIMEOUT_SECONDS}s"
            ),
        )
        return result

    remote_details = get_instance_remote_connection_info(instance_model)
    assert remote_details is not None

    try:
        pkeys = ssh_keys_to_pkeys(remote_details.ssh_keys)
        ssh_proxy_pkeys = None
        if remote_details.ssh_proxy_keys is not None:
            ssh_proxy_pkeys = ssh_keys_to_pkeys(remote_details.ssh_proxy_keys)
    except (ValueError, PasswordRequiredException):
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Unsupported private SSH key type",
        )
        return result

    authorized_keys = [pkey.public.strip() for pkey in remote_details.ssh_keys]
    authorized_keys.append(instance_model.project.ssh_public_key.strip())

    try:
        future = run_async(
            _deploy_instance,
            remote_details,
            pkeys,
            ssh_proxy_pkeys,
            authorized_keys,
        )
        health, host_info, arch = await asyncio.wait_for(future, timeout=20 * 60)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        logger.warning(
            "%s: deploy timeout when adding SSH instance: %s",
            fmt(instance_model),
            repr(exc),
        )
        return result
    except SSHProvisioningError as exc:
        logger.warning(
            "%s: provisioning error when adding SSH instance: %s",
            fmt(instance_model),
            repr(exc),
        )
        return result
    except Exception:
        logger.exception("%s: unexpected error when adding SSH instance", fmt(instance_model))
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Unexpected error when adding SSH instance",
        )
        return result

    instance_type = host_info_to_instance_type(host_info, arch)
    try:
        instance_network, internal_ip = _resolve_ssh_instance_network(instance_model, host_info)
    except _SSHInstanceNetworkResolutionError as exc:
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message=str(exc),
        )
        return result

    divisible, blocks = is_divisible_into_blocks(
        cpu_count=instance_type.resources.cpus,
        gpu_count=len(instance_type.resources.gpus),
        blocks="auto" if instance_model.total_blocks is None else instance_model.total_blocks,
    )
    if not divisible:
        set_status_update(
            update_map=result.instance_update_map,
            instance_model=instance_model,
            new_status=InstanceStatus.TERMINATED,
            termination_reason=InstanceTerminationReason.ERROR,
            termination_reason_message="Cannot split into blocks",
        )
        return result

    region = instance_model.region
    assert region is not None
    job_provisioning_data = JobProvisioningData(
        backend=BackendType.REMOTE,
        instance_type=instance_type,
        instance_id="instance_id",
        hostname=remote_details.host,
        region=region,
        price=0,
        internal_ip=internal_ip,
        instance_network=instance_network,
        username=remote_details.ssh_user,
        ssh_port=remote_details.port,
        dockerized=True,
        backend_data=None,
        ssh_proxy=remote_details.ssh_proxy,
    )
    instance_offer = InstanceOfferWithAvailability(
        backend=BackendType.REMOTE,
        instance=instance_type,
        region=region,
        price=0,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.SHIM,
    )

    set_status_update(
        update_map=result.instance_update_map,
        instance_model=instance_model,
        new_status=InstanceStatus.IDLE if health else InstanceStatus.PROVISIONING,
    )
    result.instance_update_map["backend"] = BackendType.REMOTE
    result.instance_update_map["price"] = 0
    result.instance_update_map["offer"] = instance_offer.json()
    result.instance_update_map["job_provisioning_data"] = job_provisioning_data.json()
    result.instance_update_map["started_at"] = NOW_PLACEHOLDER
    result.instance_update_map["total_blocks"] = blocks
    return result


class _SSHInstanceNetworkResolutionError(Exception):
    pass


def _resolve_ssh_instance_network(
    instance_model: InstanceModel,
    host_info: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    instance_network = None
    internal_ip = None
    try:
        default_job_provisioning_data = JobProvisioningData.__response__.parse_raw(
            instance_model.job_provisioning_data
        )
        instance_network = default_job_provisioning_data.instance_network
        internal_ip = default_job_provisioning_data.internal_ip
    except ValidationError:
        pass

    host_network_addresses = host_info.get("addresses", [])
    if internal_ip is None:
        internal_ip = get_ip_from_network(
            network=instance_network,
            addresses=host_network_addresses,
        )
    if instance_network is not None and internal_ip is None:
        raise _SSHInstanceNetworkResolutionError(
            "Failed to locate internal IP address on the given network"
        )
    if internal_ip is not None and not is_ip_among_addresses(
        ip_address=internal_ip,
        addresses=host_network_addresses,
    ):
        raise _SSHInstanceNetworkResolutionError(
            "Specified internal IP not found among instance interfaces"
        )
    return instance_network, internal_ip


def _deploy_instance(
    remote_details: RemoteConnectionInfo,
    pkeys: list[PKey],
    ssh_proxy_pkeys: Optional[list[PKey]],
    authorized_keys: list[str],
) -> tuple[InstanceCheck, dict[str, Any], GoArchType]:
    with get_paramiko_connection(
        remote_details.ssh_user,
        remote_details.host,
        remote_details.port,
        pkeys,
        remote_details.ssh_proxy,
        ssh_proxy_pkeys,
    ) as client:
        logger.debug("Connected to %s %s", remote_details.ssh_user, remote_details.host)

        arch = detect_cpu_arch(client)
        logger.debug("%s: CPU arch is %s", remote_details.host, arch)

        shim_pre_start_commands = get_shim_pre_start_commands(arch=arch)
        run_pre_start_commands(client, shim_pre_start_commands, authorized_keys)
        logger.debug("The script for installing dstack has been executed")

        shim_envs = get_shim_env(arch=arch)
        try:
            fleet_configuration_envs = remote_details.env.as_dict()
        except ValueError as exc:
            raise SSHProvisioningError(f"Invalid Env: {exc}") from exc
        shim_envs.update(fleet_configuration_envs)
        dstack_working_dir = get_dstack_working_dir()
        dstack_shim_binary_path = get_dstack_shim_binary_path()
        dstack_runner_binary_path = get_dstack_runner_binary_path()
        upload_envs(client, dstack_working_dir, shim_envs)
        logger.debug("The dstack-shim environment variables have been installed")

        remove_host_info_if_exists(client, dstack_working_dir)
        remove_dstack_runner_if_exists(client, dstack_runner_binary_path)

        run_shim_as_systemd_service(
            client=client,
            binary_path=dstack_shim_binary_path,
            working_dir=dstack_working_dir,
            dev=settings.DSTACK_VERSION is None,
        )

        host_info = get_host_info(client, dstack_working_dir)
        logger.debug("Received a host_info %s", host_info)

        healthcheck_out = get_shim_healthcheck(client)
        try:
            healthcheck = HealthcheckResponse.__response__.parse_raw(healthcheck_out)
        except ValueError as exc:
            raise SSHProvisioningError(f"Cannot parse HealthcheckResponse: {exc}") from exc
        instance_check = runner_client.healthcheck_response_to_instance_check(healthcheck)
        return instance_check, host_info, arch
