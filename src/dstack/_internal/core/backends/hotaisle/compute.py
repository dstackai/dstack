import shlex
import subprocess
import tempfile
from typing import Any, List, Optional

import gpuhunt
from gpuhunt.providers.hotaisle import HotAisleProvider

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.hotaisle.api_client import HotAisleAPIClient
from dstack._internal.core.backends.hotaisle.models import HotAisleConfig
from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import (
    CoreModel,
    validate_extra_ignore,
    validate_json_extra_ignore,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


SUPPORTED_GPUS = ["MI300X"]
SSH_CONNECT_TIMEOUT_SECONDS = 10
SSH_LAUNCH_TIMEOUT_SECONDS = 60


class HotAisleCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    Compute,
):
    def __init__(self, config: HotAisleConfig):
        super().__init__()
        self.config = config
        self.api_client = HotAisleAPIClient(config.creds.api_key, config.team_handle)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(
            HotAisleProvider(api_key=config.creds.api_key, team_handle=config.team_handle)
        )

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.HOTAISLE,
            locations=self.config.regions or None,
            catalog=self.catalog,
            extra_filter=_supported_instances,
        )
        return [
            offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            for offer in offers
        ]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        project_ssh_key = instance_config.ssh_keys[0]
        self.api_client.upload_ssh_key(project_ssh_key.public)
        offer_backend_data = validate_extra_ignore(
            HotAisleOfferBackendData, instance_offer.backend_data
        )
        if offer_backend_data.bare_metal_specs is not None:
            server_data = self.api_client.reserve_bare_metal_server(
                specs=offer_backend_data.bare_metal_specs,
                description=instance_config.instance_name,
            )
            # The deployment ID identifies this reservation, the name identifies the server.
            instance_id = server_data["deployment_id"]
            ip_address = server_data["ip_address"]
        else:
            vm_data = self.api_client.create_virtual_machine(
                get_or_error(offer_backend_data.vm_specs)
            )
            instance_id = vm_data["name"]
            ip_address = vm_data["ip_address"]
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="hotaisle",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=HotAisleInstanceBackendData(
                ip_address=ip_address,
                bare_metal=offer_backend_data.bare_metal_specs is not None,
            ).model_dump_json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        backend_data = HotAisleInstanceBackendData.load(provisioning_data.backend_data)
        if backend_data.bare_metal:
            server_data = self.api_client.get_bare_metal_server(provisioning_data.instance_id)
            os_install_status = (server_data.get("os_status") or {}).get("os_install_status")
            if os_install_status == "failed":
                raise ProvisioningError("Hot Aisle bare metal server OS installation failed")
            if os_install_status != "installed":
                return
        elif self.api_client.get_vm_state(provisioning_data.instance_id) != "running":
            return
        # Retried on the next check until the shim starts.
        if not _start_runner(
            hostname=backend_data.ip_address,
            project_ssh_private_key=project_ssh_private_key,
            arch=provisioning_data.instance_type.resources.cpu_arch,
        ):
            return
        provisioning_data.hostname = backend_data.ip_address

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        if backend_data is not None and HotAisleInstanceBackendData.load(backend_data).bare_metal:
            self.api_client.release_bare_metal_server(instance_id)
            return
        vm_name = instance_id
        self.api_client.terminate_virtual_machine(vm_name)


def _start_runner(
    hostname: str,
    project_ssh_private_key: str,
    arch: Optional[str],
) -> bool:
    commands = get_shim_commands(arch=arch)
    launch_command = "sudo sh -c " + shlex.quote(" && ".join(commands))
    return _launch_runner(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
        launch_command=launch_command,
    )


def _launch_runner(
    hostname: str,
    ssh_private_key: str,
    launch_command: str,
) -> bool:
    daemonized_command = f"{launch_command.rstrip('&')} >/tmp/dstack-shim.log 2>&1 & disown"
    return _run_ssh_command(
        hostname=hostname,
        ssh_private_key=ssh_private_key,
        command=daemonized_command,
    )


def _run_ssh_command(hostname: str, ssh_private_key: str, command: str) -> bool:
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-F",
                    "none",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}",
                    "-o",
                    "ConnectionAttempts=1",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "LogLevel=ERROR",
                    "-i",
                    f.name,
                    f"hotaisle@{hostname}",
                    command,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=SSH_LAUNCH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.debug("Timed out running SSH command on Hot Aisle instance %s", hostname)
            return False
    if proc.returncode != 0:
        logger.debug(
            "SSH command failed on Hot Aisle instance %s: exit_code=%s stderr=%r",
            hostname,
            proc.returncode,
            proc.stderr[-1000:],
        )
        return False
    return True


def _supported_instances(offer: InstanceOffer) -> bool:
    return len(offer.instance.resources.gpus) > 0 and all(
        gpu.name in SUPPORTED_GPUS for gpu in offer.instance.resources.gpus
    )


class HotAisleInstanceBackendData(CoreModel):
    ip_address: str
    bare_metal: bool = False

    @classmethod
    def load(cls, raw: Optional[str]) -> "HotAisleInstanceBackendData":
        assert raw is not None
        return validate_json_extra_ignore(cls, raw)


class HotAisleOfferBackendData(CoreModel):
    vm_specs: Optional[dict[str, Any]] = None
    bare_metal_specs: Optional[dict[str, Any]] = None
