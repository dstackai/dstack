import time
from typing import List, Optional

import requests

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.cudo.api_client import CudoApiClient
from dstack._internal.core.backends.cudo.config import CudoConfig
from dstack._internal.core.errors import BackendError, NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_WAIT_FOR_INSTANCE_ATTEMPTS = 30
_WAIT_FOR_INSTANCE_INTERVAL = 2


class CudoCompute(Compute):
    def __init__(self, config: CudoConfig):
        self.config = config
        self.api_client = CudoApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CUDO,
            requirements=requirements,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
            if offer.region not in ["in-hyderabad-1"]
        ]
        return offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_instance_name(run, job),
            ssh_keys=[
                SSHKey(public=run.run_spec.ssh_key_pub.strip()),
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        launched_instance_info = self.create_instance(instance_offer, instance_config)
        return launched_instance_info

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> LaunchedInstanceInfo:
        public_keys = instance_config.get_public_keys()
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        commands = get_shim_commands(authorized_keys=public_keys)
        gpus_no = len(instance_offer.instance.resources.gpus)
        shim_commands = " ".join([" && ".join(commands)])
        startup_script = (
            shim_commands if gpus_no > 0 else f"{install_docker_script()} && {shim_commands}"
        )

        vm_id = f"{instance_config.instance_name}-{instance_offer.region}"

        try:
            resp_data = self.api_client.create_virtual_machine(
                project_id=self.config.project_id,
                boot_disk_storage_class="STORAGE_CLASS_NETWORK",
                boot_disk_size_gib=disk_size,
                book_disk_id=f"{instance_config.instance_name}_{instance_offer.region}_disk_id",
                boot_disk_image_id=_get_image_id(gpus_no > 0),
                data_center_id=instance_offer.region,
                gpus=gpus_no,
                machine_type=instance_offer.instance.name,
                memory_gib=memory_size,
                vcpus=instance_offer.instance.resources.cpus,
                vm_id=vm_id,
                start_script=startup_script,
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

        for _ in range(_WAIT_FOR_INSTANCE_ATTEMPTS):
            vm = self.api_client.get_vm(self.config.project_id, vm_id)
            if vm["VM"]["state"] == "FAILED":
                raise BackendError("VM entered FAILED state", vm)
            if vm["VM"]["state"] == "ACTIVE":
                break
            time.sleep(_WAIT_FOR_INSTANCE_INTERVAL)
        else:
            raise BackendError("Failed waiting for VM to become ACTIVE", vm)

        launched_instance = LaunchedInstanceInfo(
            instance_id=resp_data["id"],
            ip_address=vm["VM"]["publicIpAddress"],
            region=resp_data["vm"]["regionId"],
            ssh_port=22,
            username="root",
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


def _get_image_id(cuda: bool) -> str:
    image_name = "ubuntu-2204-nvidia-535-docker-v20240214" if cuda else "ubuntu-2204"
    return image_name


def install_docker_script():
    commands = 'export DEBIAN_FRONTEND="noninteractive" && mkdir -p /etc/apt/keyrings && curl --max-time 60 -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && apt-get update && apt-get --assume-yes install docker-ce docker-ce-cli containerd.io docker-compose-plugin'
    return commands
