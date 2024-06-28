from typing import Dict, List, Optional

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.datacrunch.api_client import DataCrunchAPIClient
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.logging import get_logger

logger = get_logger("datacrunch.compute")


class DataCrunchCompute(Compute):
    def __init__(self, config: DataCrunchConfig):
        self.config = config
        self.api_client = DataCrunchAPIClient(config.creds.client_id, config.creds.client_secret)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.DATACRUNCH,
            locations=self.config.regions,
            requirements=requirements,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        raw_availabilities: List[Dict] = self.api_client.client.instances.get_availabilities()

        region_availabilities = {}
        for location in raw_availabilities:
            location_code = location["location_code"]
            availabilities = location["availabilities"]
            if location_code not in self.config.regions:
                continue
            for name in availabilities:
                key = (name, location_code)
                region_availabilities[key] = InstanceAvailability.AVAILABLE

        availability_offers = []
        for offer in offers:
            key = (offer.instance.name, offer.region)
            availability = region_availabilities.get(key, InstanceAvailability.NOT_AVAILABLE)
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )

        return availability_offers

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        public_keys = instance_config.get_public_keys()
        ssh_ids = []
        for ssh_public_key in public_keys:
            ssh_ids.append(
                # datacrunch allows you to use the same name
                self.api_client.get_or_create_ssh_key(
                    name=f"dstack-{instance_config.instance_name}.key",
                    public_key=ssh_public_key,
                )
            )

        commands = get_shim_commands(authorized_keys=public_keys)

        startup_script = " ".join([" && ".join(commands)])
        script_name = f"dstack-{instance_config.instance_name}.sh"

        logger.debug("startup script:", startup_script)

        startup_script_ids = self.api_client.get_or_create_startup_scrpit(
            name=script_name, script=startup_script
        )

        # Id of image "Ubuntu 22.04 + CUDA 12.0 + Docker"
        # from API https://datacrunch.stoplight.io/docs/datacrunch-public/c46ab45dbc508-get-all-image-types
        image_name = "2088da25-bb0d-41cc-a191-dccae45d96fd"

        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)

        instance = self.api_client.deploy_instance(
            instance_type=instance_offer.instance.name,
            ssh_key_ids=ssh_ids,
            startup_script_id=startup_script_ids,
            hostname=instance_config.instance_name,
            description=instance_config.instance_name,
            image=image_name,
            disk_size=disk_size,
            location=instance_offer.region,
        )

        logger.debug(
            "deploy_instance",
            {
                "instance_type": instance_offer.instance.name,
                "ssh_key_ids": ssh_ids,
                "startup_script_id": startup_script_ids,
                "hostname": instance_config.instance_name,
                "description": instance_config.instance_name,
                "image": image_name,
                "disk_size": disk_size,
                "location": instance_offer.region,
            },
        )

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance.id,
            hostname=None,
            internal_ip=None,
            region=instance.location,
            price=instance_offer.price,
            username="root",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

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
            instance_name=job.job_spec.job_name,  # TODO: generate name
            ssh_keys=[
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )
        return self.create_instance(instance_offer, instance_config)

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        self.api_client.delete_instance(instance_id)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance = self.api_client.get_instance_by_id(provisioning_data.instance_id)
        if instance is not None and instance.status == "running":
            provisioning_data.hostname = instance.ip
