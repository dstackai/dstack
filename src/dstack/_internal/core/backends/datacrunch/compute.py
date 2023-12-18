from typing import Dict, List, Optional

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import get_shim_commands
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.datacrunch.api_client import DataCrunchAPIClient
from dstack._internal.core.backends.datacrunch.config import DataCrunchConfig
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


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
        raw_availabilities: List[
            Dict
        ] = self.api_client.client.instances.get_availabilities()  # type: ignore

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

    def get_instance_state(self, instance_id: str, region: str) -> InstanceState:
        instance = self.api_client.client.instances.get_by_id(instance_id)

        # TODO 404 NOT_FOUND = "not_found"
        # TODO other statuses

        state_map = {
            "provisioning": InstanceState.PROVISIONING,
            "running": InstanceState.RUNNING,
            "offline": InstanceState.STOPPED,
            "discontinued": InstanceState.TERMINATED,
        }
        status = state_map.get(instance.status, InstanceState.NOT_FOUND)
        return status

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        ssh_ids = []
        ssh_ids.append(
            self.api_client.get_or_create_ssh_key(
                name=f"dstack-{job.job_spec.job_name}.key",
                public_key=run.run_spec.ssh_key_pub.strip(),
            )
        )
        ssh_ids.append(
            self.api_client.get_or_create_ssh_key(
                name=f"dstack-{job.job_spec.job_name}.key",
                public_key=project_ssh_public_key.strip(),
            )
        )

        commands = get_shim_commands(
            backend=BackendType.DATACRUNCH,
            image_name=job.job_spec.image_name,
            authorized_keys=[
                run.run_spec.ssh_key_pub.strip(),
                project_ssh_public_key.strip(),
            ],
            registry_auth_required=job.job_spec.registry_auth is not None,
        )

        startup_script = " ".join([" && ".join(commands)])
        script_name = f"dstack-{job.job_spec.job_name}.sh"
        startup_script_ids = self.api_client.get_or_create_startup_scrpit(
            name=script_name, script=startup_script
        )

        name = job.job_spec.job_name

        # Id of image "Ubuntu 22.04 + CUDA 12.0 + Docker"
        # from API https://datacrunch.stoplight.io/docs/datacrunch-public/c46ab45dbc508-get-all-image-types
        image_name = "2088da25-bb0d-41cc-a191-dccae45d96fd"

        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        instance = self.api_client.deploy_instance(
            instance_type=instance_offer.instance.name,
            ssh_key_ids=ssh_ids,
            startup_script_id=startup_script_ids,
            hostname=name,
            description=name,
            image=image_name,
            disk_size=disk_size,
            location=instance_offer.region,
        )

        running_instance = self.api_client.wait_for_instance(instance.id)
        if running_instance is None:
            raise BackendError(f"Wait instance {instance.id!r} timeout")

        launched_instance = LaunchedInstanceInfo(
            instance_id=running_instance.id,
            ip_address=running_instance.ip,
            region=running_instance.location,
            ssh_port=22,
            username="root",
            dockerized=True,
            backend_data=None,
        )

        return launched_instance

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        self.api_client.delete_instance(instance_id)
