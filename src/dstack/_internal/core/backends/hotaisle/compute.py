import shlex
import subprocess
import tempfile
from threading import Thread
from typing import List, Optional

import gpuhunt
from gpuhunt.providers.hotaisle import HotAisleProvider

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.hotaisle.api_client import HotaisleAPIClient
from dstack._internal.core.backends.hotaisle.models import HotaisleConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

MAX_INSTANCE_NAME_LEN = 60


class HotaisleCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: HotaisleConfig):
        super().__init__()
        self.config = config
        self.api_client = HotaisleAPIClient(config.creds.api_key, config.team_handle)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(
            HotAisleProvider(api_key=config.creds.api_key, team_handle=config.team_handle)
        )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.HOTAISLE,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self.catalog,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
        ]
        return offers

    def get_payload_from_offer(self, instance_type) -> dict:
        # Only two instance types are available in Hotaisle with CPUs: 8-core and 13-core. Other fields are
        # not configurable.
        cpu_cores = instance_type.resources.cpus
        if cpu_cores == 8:
            cpu_model = "Xeon Platinum 8462Y+"
            frequency = 2800000000
        else:  # cpu_cores == 13
            cpu_model = "Xeon Platinum 8470"
            frequency = 2000000000

        return {
            "cpu_cores": cpu_cores,
            "cpus": {
                "count": 1,
                "manufacturer": "Intel",
                "model": cpu_model,
                "cores": cpu_cores,
                "frequency": frequency,
            },
            "disk_capacity": 13194139533312,
            "ram_capacity": 240518168576,
            "gpus": [
                {
                    "count": len(instance_type.resources.gpus),
                    "manufacturer": "AMD",
                    "model": "MI300X",
                }
            ],
        }

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )
        project_ssh_key = instance_config.ssh_keys[0]
        self.api_client.upload_ssh_key(project_ssh_key.public)
        vm_payload = self.get_payload_from_offer(instance_offer.instance)
        vm_data = self.api_client.create_virtual_machine(vm_payload, instance_name)
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
            backend_data=vm_data["ip_address"],
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
                provisioning_data.hostname = provisioning_data.backend_data
            commands = get_shim_commands(
                authorized_keys=[project_ssh_public_key],
                arch=provisioning_data.instance_type.resources.cpu_arch,
            )
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
    _setup_instance(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
    )
    _launch_runner(
        hostname=hostname,
        ssh_private_key=project_ssh_private_key,
        launch_command=launch_command,
    )


def _setup_instance(
    hostname: str,
    ssh_private_key: str,
):
    setup_commands = ("sudo apt-get update",)
    _run_ssh_command(
        hostname=hostname, ssh_private_key=ssh_private_key, command=" && ".join(setup_commands)
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
