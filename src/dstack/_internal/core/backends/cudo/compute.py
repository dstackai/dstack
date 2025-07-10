from typing import List, Optional

import requests

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.cudo.api_client import CudoApiClient
from dstack._internal.core.backends.cudo.models import CudoConfig
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
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


MAX_RESOURCE_NAME_LEN = 30


class CudoCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: CudoConfig):
        super().__init__()
        self.config = config
        self.api_client = CudoApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CUDO,
            locations=self.config.regions,
            requirements=requirements,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
            # in-hyderabad-1 is known to have provisioning issues
            if offer.region not in ["in-hyderabad-1"]
        ]
        return offers

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        vm_id = generate_unique_instance_name(instance_config, max_length=MAX_RESOURCE_NAME_LEN)
        public_keys = instance_config.get_public_keys()
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        gpus_no = len(instance_offer.instance.resources.gpus)
        if gpus_no > 0:
            # we'll need jq for patching /etc/docker/daemon.json, see get_shim_commands()
            commands = install_jq_commands()
        else:
            commands = install_docker_commands()
        commands += get_shim_commands(authorized_keys=public_keys)

        try:
            resp_data = self.api_client.create_virtual_machine(
                project_id=self.config.project_id,
                boot_disk_storage_class="STORAGE_CLASS_NETWORK",
                boot_disk_size_gib=disk_size,
                book_disk_id=f"{vm_id}_disk_id",
                boot_disk_image_id=_get_image_id(gpus_no > 0),
                data_center_id=instance_offer.region,
                gpus=gpus_no,
                machine_type=instance_offer.instance.name,
                memory_gib=memory_size,
                vcpus=instance_offer.instance.resources.cpus,
                vm_id=vm_id,
                start_script=" && ".join(commands),
                password=None,
                customSshKeys=public_keys,
            )
        except requests.HTTPError as e:
            try:
                details = e.response.json()
                response_code = details.get("code")
            except ValueError:
                raise BackendError(e)

            # code 3: There are no hosts available for your specified virtual machine.
            if response_code == 3:
                raise NoCapacityError(details.get("message"))
            # code 9: Vm cannot be assigned ip from network. Network full
            if response_code == 9:
                raise BackendError(details.get("message"))
            # code 6: A disk with that id already exists
            if response_code == 6:
                raise BackendError(details.get("message"))

        launched_instance = JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=resp_data["id"],
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            ssh_port=22,
            username="root",
            ssh_proxy=None,
            dockerized=True,
            backend_data=None,
        )
        return launched_instance

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        try:
            self.api_client.terminate_virtual_machine(instance_id, self.config.project_id)
        except requests.HTTPError as e:
            if e.response.status_code == requests.codes.not_found:
                logger.debug("The instance with name %s not found", instance_id)
                return
            raise BackendError(e.response.text)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        vm = self.api_client.get_vm(self.config.project_id, provisioning_data.instance_id)
        if vm["VM"]["state"] == "ACTIVE":
            provisioning_data.hostname = vm["VM"]["publicIpAddress"]
        if vm["VM"]["state"] == "FAILED":
            raise ProvisioningError("VM entered FAILED state", vm)


def _get_image_id(cuda: bool) -> str:
    image_name = "ubuntu-2204-nvidia-535-docker-v20241017" if cuda else "ubuntu-2204"
    return image_name


def install_jq_commands():
    return [
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get --assume-yes install jq",
    ]


def install_docker_commands():
    return [
        "export DEBIAN_FRONTEND=noninteractive",
        "mkdir -p /etc/apt/keyrings",
        "curl --max-time 60 -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null',
        "apt-get update",
        "apt-get --assume-yes install docker-ce docker-ce-cli containerd.io docker-compose-plugin",
    ]
