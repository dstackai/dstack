import hashlib
import subprocess
import tempfile
from threading import Thread
from typing import Dict, List, Optional

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.core.backends.lambdalabs.models import LambdaConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData, Requirements

MAX_INSTANCE_NAME_LEN = 60


class LambdaCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: LambdaConfig):
        super().__init__()
        self.config = config
        self.api_client = LambdaAPIClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.LAMBDA,
            locations=self.config.regions or None,
            requirements=requirements,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

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
        project_key_name = _add_project_ssh_key(
            api_client=self.api_client,
            project_ssh_public_key=project_ssh_key.public,
        )
        instances_ids = self.api_client.launch_instances(
            region_name=instance_offer.region,
            instance_type_name=instance_offer.instance.name,
            ssh_key_names=[project_key_name],
            name=instance_name,
            quantity=1,
            file_system_names=[],
        )
        instance_id = instances_ids[0]
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="ubuntu",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance_info = _get_instance_info(self.api_client, provisioning_data.instance_id)
        if instance_info is not None and instance_info["status"] != "booting":
            provisioning_data.hostname = instance_info["ip"]
            commands = get_shim_commands(
                authorized_keys=[project_ssh_public_key],
                arch=provisioning_data.instance_type.resources.cpu_arch,
            )
            # shim is assumed to be run under root
            launch_command = "sudo sh -c '" + "&& ".join(commands) + "'"
            thread = Thread(
                target=_start_runner,
                kwargs={
                    "hostname": instance_info["ip"],
                    "project_ssh_private_key": project_ssh_private_key,
                    "launch_command": launch_command,
                },
                daemon=True,
            )
            thread.start()

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.terminate_instances(instance_ids=[instance_id])

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        instance_availability = {
            instance_name: [
                region["name"] for region in details["regions_with_capacity_available"]
            ]
            for instance_name, details in self.api_client.list_instance_types().items()
        }
        availability_offers = []
        for offer in offers:
            availability = InstanceAvailability.NOT_AVAILABLE
            if offer.region in instance_availability.get(offer.instance.name, []):
                availability = InstanceAvailability.AVAILABLE
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )
        return availability_offers


def _add_project_ssh_key(
    api_client: LambdaAPIClient,
    project_ssh_public_key: str,
) -> str:
    ssh_keys = api_client.list_ssh_keys()
    ssh_key_names: List[str] = [k["name"] for k in ssh_keys]
    project_key_name = _add_ssh_key(api_client, ssh_key_names, project_ssh_public_key)
    return project_key_name


def _add_ssh_key(api_client: LambdaAPIClient, ssh_key_names: List[str], public_key: str) -> str:
    key_name = _get_ssh_key_name(public_key)
    if key_name in ssh_key_names:
        return key_name
    api_client.add_ssh_key(name=key_name, public_key=public_key)
    return key_name


def _get_ssh_key_name(public_key: str) -> str:
    return hashlib.sha1(public_key.encode()).hexdigest()[-16:]


def _get_instance_info(api_client: LambdaAPIClient, instance_id: str) -> Optional[Dict]:
    # TODO: use get instance https://cloud.lambdalabs.com/api/v1/docs#operation/getInstance
    instances = api_client.list_instances()
    instance_id_to_instance_map = {i["id"]: i for i in instances}
    instance = instance_id_to_instance_map.get(instance_id)
    return instance


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
    setup_commands = (
        "mkdir /home/ubuntu/.dstack",
        "sudo apt-get update",
        "sudo apt-get install -y --no-install-recommends nvidia-container-toolkit",
        "sudo install -d -m 0755 /etc/docker",
        # Workaround for https://github.com/NVIDIA/nvidia-container-toolkit/issues/48
        """echo '{"exec-opts":["native.cgroupdriver=cgroupfs"]}' | sudo tee /etc/docker/daemon.json""",
        "sudo nvidia-ctk runtime configure --runtime=docker",
        "sudo systemctl restart docker.service",  # `systemctl reload` (`kill -HUP`) won't work
    )
    _run_ssh_command(
        hostname=hostname, ssh_private_key=ssh_private_key, command=" && ".join(setup_commands)
    )


def _launch_runner(
    hostname: str,
    ssh_private_key: str,
    launch_command: str,
):
    _run_ssh_command(
        hostname=hostname,
        ssh_private_key=ssh_private_key,
        command=launch_command,
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
                f"ubuntu@{hostname}",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
