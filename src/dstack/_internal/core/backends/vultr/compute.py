import json
import time
from typing import List, Optional

import requests

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.vultr.api_client import VultrApiClient
from dstack._internal.core.backends.vultr.config import VultrConfig
from dstack._internal.core.errors import BackendError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class VultrCompute(Compute):
    def __init__(self, config: VultrConfig):
        self.config = config
        self.api_client = VultrApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.VULTR,
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
        volumes: List[Volume],
    ) -> JobProvisioningData:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_instance_name(run, job),
            ssh_keys=[SSHKey(public=project_ssh_public_key.strip())],
            user=run.user,
        )
        return self.create_instance(instance_offer, instance_config)

    def create_instance(
        self, instance_offer: InstanceOfferWithAvailability, instance_config: InstanceConfiguration
    ) -> JobProvisioningData:
        public_keys = instance_config.get_public_keys()
        commands = get_shim_commands(authorized_keys=public_keys)
        shim_commands = "#!/bin/sh\n" + " ".join([" && ".join(commands)])
        plan_type = "bare-metal" if "vbm" in instance_offer.instance.name else "vm_instance"
        try:
            instance_id = self.api_client.launch_instance(
                region=instance_offer.region,
                label=instance_config.instance_name,
                plan=instance_offer.instance.name,
                startup_script=shim_commands,
                public_keys=public_keys,
            )
        except Exception:
            raise
        # Create VPC
        # Vultr provides "enable_vpc" option during instance creation,
        # but if instance creation fails due to no-capacity, the created VPC does not
        # terminate automatically.
        vpc_id = self.api_client.get_vpc_for_region(instance_offer.region)
        if not vpc_id:
            vpc_id = self.api_client.create_vpc(instance_offer.region)

        while not self.api_client.get_vpc_id(instance_id, plan_type) and vpc_id is not None:
            time.sleep(1)
            # Vultr's limitation is that we cannot attach VPC without multiple attempts.
            logger.info("Attempting to attach instance to VPC")
            try:
                self.api_client.attach_vpc(vpc_id, instance_id, plan_type)
            except BackendError as e:
                if "plan does not support private networking" in str(e):
                    logger.warning("Plan does not support private networking.")
                    # delete created vpc
                    self.api_client.delete_vpc(vpc_id=vpc_id)
                    vpc_id = None
                else:
                    raise

        launched_instance = JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            ssh_port=22,
            username="root",
            ssh_proxy=None,
            dockerized=True,
            backend_data=json.dumps(
                {
                    "plan_type": plan_type,
                    "vpc_id": vpc_id,
                }
            ),
        )
        return launched_instance

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        plan_type = json.loads(backend_data)["plan_type"]
        vpc_id = json.loads(backend_data)["vpc_id"]
        try:
            self.api_client.terminate_instance(instance_id=instance_id, plan_type=plan_type)
            if vpc_id:
                while self.api_client.get_vpc_id(instance_id=instance_id, plan_type=plan_type):
                    time.sleep(1)
                    # Vultr provides /vpcs/detach endpoint, but is not reliable.
                    # The reliable solution is to terminate the instance and wait
                    # till the VPC gets released. Once the VPC gets released, delete the VPC.
                    logger.info("Waiting to release VPC")
                # VPC cannot be deleted without being released by the instance.
                self.api_client.delete_vpc(vpc_id=vpc_id)
        except requests.HTTPError as e:
            raise BackendError(e.response.text)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        plan_type = json.loads(provisioning_data.backend_data)["plan_type"]
        instance_data = self.api_client.get_instance(provisioning_data.instance_id, plan_type)
        # Access specific fields
        instance_status = instance_data["status"]
        instance_main_ip = instance_data["main_ip"]
        if instance_status == "active":
            provisioning_data.hostname = instance_main_ip
        if instance_status == "failed":
            raise ProvisioningError("VM entered FAILED state")
