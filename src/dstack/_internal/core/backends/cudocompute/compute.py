import time
from typing import List, Optional

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_instance_name,
    get_shim_commands,
    logger,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.cudocompute.api_client import CudoComputeApiClient
from dstack._internal.core.backends.cudocompute.config import CudoComputeConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class CudoComputeCompute(Compute):
    def __init__(self, config: CudoComputeConfig):
        self.config = config
        self.api_client = CudoComputeApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CUDOCOMPUTE,
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
            instance_name=get_instance_name(run, job),  # TODO: generate name
            ssh_keys=[
                SSHKey(public=run.run_spec.ssh_key_pub.strip()),
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        launched_instance_info = self.create_instance(instance_offer, instance_config)
        return launched_instance_info

    # def run_job(self, run: Run, job: Job, instance_offer: InstanceOfferWithAvailability,
    #                 project_ssh_public_key: str,
    #                 project_ssh_private_key: str) -> LaunchedInstanceInfo:
    #     # disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
    #     memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
    #
    #     commands = get_shim_commands(
    #         backend=BackendType.CUDOCOMPUTE,
    #         image_name=job.job_spec.image_name,
    #         authorized_keys=[
    #             run.run_spec.ssh_key_pub.strip(),
    #             project_ssh_public_key.strip(),
    #         ],
    #         registry_auth_required=job.job_spec.registry_auth is not None,
    #     )
    #
    #     startup_script = " ".join([" && ".join(commands)])
    #
    #     resp_data = self.api_client.create_virtual_machine(
    #         project_id=self.config.project_id,
    #         boot_disk_storage_class="STORAGE_CLASS_NETWORK",
    #         boot_disk_size_gib=100,
    #         book_disk_id="dstack_disk_id",
    #         boot_disk_image_id="ubuntu-2204-nvidia-535-docker-v20240214",
    #         data_center_id=instance_offer.region,
    #         gpu_model=instance_offer.instance.resources.gpus[0].name,
    #         gpus=len(instance_offer.instance.resources.gpus),
    #         machine_type=instance_offer.instance.name,
    #         memory_gib=memory_size,
    #         vcpus=instance_offer.instance.resources.cpus,
    #         vm_id="dstack-vm-id",
    #         start_script=startup_script,
    #         password=None,
    #         customSshKeys=[
    #             f"{run.run_spec.ssh_key_pub.strip()}",
    #             f"{project_ssh_public_key.strip()}",
    #             "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDKbMDLDHR6qiczSlnLXO0BlhdIa0Ixc855VqlPlq8DO3+4+l8qvnb4jhnVBDkX3+iiofVzEMRV9x1D2F7TIK/grL10TZ8pP2ehTeGbuuKsR5jPA0ZfQgh60VpMd3bbCfzTpRkHRksh7s1w2n8E3EO7zhtuta6wj9H3vxV87+7wYblHM/zLZVuoQWThpKnzqN9Y06j8IOb/UZU0ImOxKIRSlf98i9Lyh8awwYczUJFyBgwWiWo48/h5+l+uhUkdc8OrkvSwPl+C9w4NmtRKGWK01F1KbkqbSuOhja+W9mx31EC+lhiMhJ4mdqmYi59wzfWtJiqxSJKwCR5yExbtvcvUcWmXiDcxygEkaC7HlJwhbrJLT4XPaQlEBrUeQG2vyUh6SDlLl8Kmx0IQhtUje5s7PV9Y+2EJwoOBL8CKJplSyjTXcC3TNXi+jsTQNYMzcNHRHTPlTzvj/nwfPDVMJ1iGEClm6jTi/9t1sFo0c9aIzucU5s/KKWlPwklhatGWcps= bihan@Bihans-MacBook-Pro.local",
    #         ],
    #     )
    #     logger.info(
    #         "Running job in LocalBackend. To start processing, run: `"
    #         f"DSTACK_BACKEND=local "
    #         "DSTACK_RUNNER_LOG_LEVEL=6 "
    #         f"DSTACK_RUNNER_VERSION={get_dstack_runner_version()} "
    #         f"DSTACK_IMAGE_NAME={job.job_spec.image_name} ",
    #     )
    #
    #     vm = self.api_client.get_vm("dstack-test", "dstack-vm-id")
    #     # Loop as long as the VM state is 'ACTIVE'
    #     while vm["VM"]["state"] == "ACTIVE":
    #         time.sleep(1)
    #         logger.info("Fetching VM state")
    #         vm = self.api_client.get_vm("dstack-test", "dstack-vm-id")
    #
    #     launched_instance = LaunchedInstanceInfo(
    #         instance_id=resp_data["id"],
    #         ip_address=vm["VM"]["publicIpAddress"],
    #         region=resp_data["vm"]["regionId"],
    #         ssh_port=22,
    #         username="root",
    #         dockerized=True,
    #         backend_data=None,
    #     )
    #     return launched_instance

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> LaunchedInstanceInfo:
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)

        commands = get_shim_commands(authorized_keys=instance_config.ssh_keys)

        startup_script = " ".join([" && ".join(commands)])
        resp_data = self.api_client.create_virtual_machine(
            project_id=self.config.project_id,
            boot_disk_storage_class="STORAGE_CLASS_NETWORK",
            boot_disk_size_gib=100,
            book_disk_id="dstack_disk_id",
            boot_disk_image_id="ubuntu-2204-nvidia-535-docker-v20240214",
            data_center_id=instance_offer.region,
            gpu_model=instance_offer.instance.resources.gpus[0].name,
            gpus=len(instance_offer.instance.resources.gpus),
            machine_type=instance_offer.instance.name,
            memory_gib=memory_size,
            vcpus=instance_offer.instance.resources.cpus,
            vm_id="dstack-vm-id",
            start_script=startup_script,
            password=None,
            customSshKeys=instance_config.ssh_keys,
        )

        vm = self.api_client.get_vm("dstack-test", "dstack-vm-id")
        # Loop as long as the VM state is 'ACTIVE'
        while vm["VM"]["state"] == "ACTIVE":
            time.sleep(1)
            logger.info("Fetching VM state")
            vm = self.api_client.get_vm("dstack-test", "dstack-vm-id")

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
        self.api_client.terminate_virtual_machine(instance_id, self.config.project_id)
