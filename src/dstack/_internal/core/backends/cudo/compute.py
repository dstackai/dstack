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

        startup_script = " ".join([" && ".join(commands)])
        try:
            resp_data = self.api_client.create_virtual_machine(
                project_id=self.config.project_id,
                boot_disk_storage_class="STORAGE_CLASS_NETWORK",
                boot_disk_size_gib=disk_size,
                book_disk_id=f"{instance_config.instance_name}_disk_id",
                boot_disk_image_id="ubuntu-2204-nvidia-535-docker-v20240214",
                data_center_id=instance_offer.region,
                gpus=len(instance_offer.instance.resources.gpus),
                machine_type=instance_offer.instance.name,
                memory_gib=memory_size,
                vcpus=instance_offer.instance.resources.cpus,
                vm_id=instance_config.instance_name,
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

        vm = self.api_client.get_vm(self.config.project_id, instance_config.instance_name)
        # Wait until VM State is Active. This is necessary to get the ip_address.
        while vm["VM"]["state"] != "ACTIVE":
            time.sleep(1)
            vm = self.api_client.get_vm(self.config.project_id, instance_config.instance_name)

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
