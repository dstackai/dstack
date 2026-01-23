import shlex
import subprocess
import tempfile
from threading import Thread
from typing import Any, List, Optional

import gpuhunt
from gpuhunt.providers.hotaisle import HotAisleProvider

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.hotaisle.api_client import HotAisleAPIClient
from dstack._internal.core.backends.hotaisle.models import HotAisleConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


SUPPORTED_GPUS = ["MI300X"]


class HotAisleCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
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

    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.HOTAISLE,
            locations=self.config.regions or None,
            catalog=self.catalog,
            extra_filter=_supported_instances,
        )
        return [
            InstanceOfferWithAvailability(
                **offer.dict(),
                availability=InstanceAvailability.AVAILABLE,
            )
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
        offer_backend_data: HotAisleOfferBackendData = (
            HotAisleOfferBackendData.__response__.parse_obj(instance_offer.backend_data)
        )
        vm_data = self.api_client.create_virtual_machine(offer_backend_data.vm_specs)
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=vm_data["name"],
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="hotaisle",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=HotAisleInstanceBackendData(ip_address=vm_data["ip_address"]).json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        vm_state = self.api_client.get_vm_state(provisioning_data.instance_id)
        if vm_state == "running":
            if provisioning_data.hostname is None and provisioning_data.backend_data:
                backend_data = HotAisleInstanceBackendData.load(provisioning_data.backend_data)
                provisioning_data.hostname = backend_data.ip_address
            commands = get_shim_commands(arch=provisioning_data.instance_type.resources.cpu_arch)
            launch_command = "sudo sh -c " + shlex.quote(" && ".join(commands))
            thread = Thread(
                target=_start_runner,
                kwargs={
                    "hostname": provisioning_data.hostname,
                    "project_ssh_private_key": project_ssh_private_key,
                    "launch_command": launch_command,
                },
                daemon=True,
            )
            thread.start()

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        vm_name = instance_id
        self.api_client.terminate_virtual_machine(vm_name)


def _start_runner(
    hostname: str,
    project_ssh_private_key: str,
    launch_command: str,
):
    _launch_runner(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
        launch_command=launch_command,
    )


def _launch_runner(
    hostname: str,
    ssh_private_key: str,
    launch_command: str,
):
    daemonized_command = f"{launch_command.rstrip('&')} >/tmp/dstack-shim.log 2>&1 & disown"
    _run_ssh_command(
        hostname=hostname,
        ssh_private_key=ssh_private_key,
        command=daemonized_command,
    )


def _run_ssh_command(hostname: str, ssh_private_key: str, command: str):
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        subprocess.run(
            [
                "ssh",
                "-F",
                "none",
                "-o",
                "StrictHostKeyChecking=no",
                "-i",
                f.name,
                f"hotaisle@{hostname}",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _supported_instances(offer: InstanceOffer) -> bool:
    return len(offer.instance.resources.gpus) > 0 and all(
        gpu.name in SUPPORTED_GPUS for gpu in offer.instance.resources.gpus
    )


class HotAisleInstanceBackendData(CoreModel):
    ip_address: str

    @classmethod
    def load(cls, raw: Optional[str]) -> "HotAisleInstanceBackendData":
        assert raw is not None
        return cls.__response__.parse_raw(raw)


class HotAisleOfferBackendData(CoreModel):
    vm_specs: dict[str, Any]
